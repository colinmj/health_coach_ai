"""Sync Withings body composition data into PostgreSQL.

Run:
    python -m sync.withings

Each run is idempotent. Requires WITHINGS_ACCESS_TOKEN and WITHINGS_REFRESH_TOKEN
in .env — run `python -m sync.withings_auth` first if they are missing.
"""

import os
from datetime import datetime, timezone

from typing import Any

import psycopg
from dotenv import load_dotenv

from clients.withings import WithingsClient
from db.schema import get_connection, get_request_user_id, set_current_user_id, get_cli_user_id, init_db
from sync.utils import get_integration_tokens, get_last_synced_at, save_integration_tokens, update_last_synced_at

load_dotenv()

# Maps Withings measure type codes to body_measurements column names
MEASURE_TYPES = {
    1:  "weight_kg",
    5:  "fat_free_mass_kg",
    6:  "fat_ratio",
    8:  "fat_mass_kg",
    76: "muscle_mass_kg",
    77: "hydration_kg",
    88: "bone_mass_kg",
}


def _decode(value: int, unit: int) -> float:
    """Convert Withings fixed-point value: real = value × 10^unit."""
    return value * (10 ** unit)


def _upsert_measurement(grp: dict, conn: psycopg.Connection[dict[str, Any]], user_id: int) -> None:
    """Insert or update a body_measurements row from a measuregrp dict."""
    grp_id = grp["grpid"]
    unix_ts = grp["date"]

    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    measured_at = dt.isoformat()
    date = dt.strftime("%Y-%m-%d")

    # Map measure list to column values; unmeasured columns stay None
    columns: dict[str, float | None] = {col: None for col in MEASURE_TYPES.values()}
    for m in grp.get("measures", []):
        col = MEASURE_TYPES.get(m["type"])
        if col is not None:
            columns[col] = _decode(m["value"], m["unit"])

    conn.execute(
        """
        INSERT INTO body_measurements
            (user_id, external_id, measured_at, date, source,
             weight_kg, fat_free_mass_kg, fat_ratio, fat_mass_kg,
             muscle_mass_kg, hydration_kg, bone_mass_kg)
        VALUES (%s, %s, %s, %s, 'withings', %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id, source, external_id) DO UPDATE SET
            measured_at      = EXCLUDED.measured_at,
            date             = EXCLUDED.date,
            weight_kg        = EXCLUDED.weight_kg,
            fat_free_mass_kg = EXCLUDED.fat_free_mass_kg,
            fat_ratio        = EXCLUDED.fat_ratio,
            fat_mass_kg      = EXCLUDED.fat_mass_kg,
            muscle_mass_kg   = EXCLUDED.muscle_mass_kg,
            hydration_kg     = EXCLUDED.hydration_kg,
            bone_mass_kg     = EXCLUDED.bone_mass_kg,
            synced_at        = NOW()
        """,
        (
            user_id,
            str(grp_id),
            measured_at,
            date,
            columns["weight_kg"],
            columns["fat_free_mass_kg"],
            columns["fat_ratio"],
            columns["fat_mass_kg"],
            columns["muscle_mass_kg"],
            columns["hydration_kg"],
            columns["bone_mass_kg"],
        ),
    )


def sync_withings() -> None:
    init_db()
    user_id = get_request_user_id()

    # Only fetch measurements newer than the last successful sync
    last = get_last_synced_at(user_id, "withings")
    startdate = int(last.timestamp()) if last else None
    if last:
        print(f"Incremental sync from {last.isoformat()}")

    print("Fetching body measurements from Withings…")
    access_token, refresh_token = get_integration_tokens(user_id, "withings")
    with WithingsClient(
        client_id=os.environ["WITHINGS_CLIENT_ID"],
        client_secret=os.environ["WITHINGS_CLIENT_SECRET"],
        access_token=access_token,
        refresh_token=refresh_token,
        on_token_refresh=lambda at, rt: save_integration_tokens(user_id, "withings", at, rt),
    ) as client:
        # Collect all groups then sort oldest-first for consistency
        grps = list(client.iter_body_measurements(startdate=startdate))

    grps.sort(key=lambda g: g["date"])
    print(f"  {len(grps)} measurement groups found")

    with get_connection() as conn:
        for grp in grps:
            _upsert_measurement(grp, conn, user_id)
        conn.commit()

    print(f"Body measurements synced: {len(grps)} rows")
    update_last_synced_at(user_id, "withings")
    print("Withings sync complete.")


if __name__ == "__main__":
    set_current_user_id(get_cli_user_id())
    sync_withings()
