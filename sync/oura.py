"""Sync Oura Ring sleep and readiness data into PostgreSQL.

Run:
    python -m sync.oura

Each run is idempotent. Requires an Oura Personal Access Token stored in
user_integrations.access_token — connect via Settings to provide it.
"""

from typing import Any

import psycopg
from dotenv import load_dotenv

from clients.oura import OuraClient
from db.schema import get_connection, get_local_user_id, init_db
from sync.utils import get_integration_tokens, get_last_synced_at, update_last_synced_at

load_dotenv()


# ---------------------------------------------------------------------------
# DB helpers — sleep
# ---------------------------------------------------------------------------

def _upsert_sleep(conn: psycopg.Connection[dict[str, Any]], record: dict, user_id: int) -> None:
    sleep_id = str(record["id"])
    date = record.get("day", "")
    start = record.get("bedtime_start")
    end = record.get("bedtime_end")

    # Stage durations are in seconds — convert to milliseconds
    def s_to_ms(val: int | None) -> int | None:
        return val * 1000 if val is not None else None

    values = (
        date,
        False,  # is_nap — Oura doesn't include naps in /sleep endpoint
        None,   # score_state
        start,
        end,
        s_to_ms(record.get("time_in_bed")),
        s_to_ms(record.get("awake_time")),
        s_to_ms(record.get("light_sleep_duration")),
        s_to_ms(record.get("deep_sleep_duration")),
        s_to_ms(record.get("rem_sleep_duration")),
        None,   # disturbance_count — not in v2 readiness
        None,   # sleep_performance_percentage
        record.get("efficiency"),
        record.get("average_breath"),
    )

    existing = conn.execute(
        "SELECT id FROM sleep WHERE source = 'oura' AND external_id = %s AND user_id = %s",
        (sleep_id, user_id),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE sleep
            SET date=%s, is_nap=%s, score_state=%s, start_time=%s, end_time=%s,
                total_in_bed_time_milli=%s, total_awake_time_milli=%s,
                total_light_sleep_milli=%s, total_slow_wave_sleep_milli=%s,
                total_rem_sleep_milli=%s, disturbance_count=%s,
                sleep_performance_percentage=%s, sleep_efficiency_percentage=%s,
                respiratory_rate=%s
            WHERE source='oura' AND external_id=%s AND user_id=%s
            """,
            (*values, sleep_id, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO sleep
                (user_id, external_id, date, source, is_nap, score_state, start_time, end_time,
                 total_in_bed_time_milli, total_awake_time_milli, total_light_sleep_milli,
                 total_slow_wave_sleep_milli, total_rem_sleep_milli, disturbance_count,
                 sleep_performance_percentage, sleep_efficiency_percentage, respiratory_rate)
            VALUES (%s, %s, %s, 'oura', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, sleep_id, *values),
        )


# ---------------------------------------------------------------------------
# DB helpers — readiness (recovery)
# ---------------------------------------------------------------------------

def _upsert_readiness(conn: psycopg.Connection[dict[str, Any]], record: dict, user_id: int) -> None:
    readiness_id = str(record["id"])
    date = record.get("day", "")
    contributors = record.get("contributors") or {}

    existing = conn.execute(
        "SELECT id FROM recovery WHERE source = 'oura' AND external_id = %s AND user_id = %s",
        (readiness_id, user_id),
    ).fetchone()

    values = (
        date,
        None,   # score_state
        record.get("score"),
        record.get("average_hrv"),
        record.get("lowest_heart_rate"),
        None,   # spo2_percentage — not in v2 readiness
        None,   # skin_temp_celsius
        None,   # strain
        None,   # daily_energy_kcal
    )

    if existing:
        conn.execute(
            """
            UPDATE recovery
            SET date=%s, score_state=%s, recovery_score=%s, hrv_rmssd_milli=%s,
                resting_heart_rate=%s, spo2_percentage=%s, skin_temp_celsius=%s,
                strain=%s, daily_energy_kcal=%s
            WHERE source='oura' AND external_id=%s AND user_id=%s
            """,
            (*values, readiness_id, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO recovery
                (user_id, external_id, date, source, score_state, recovery_score,
                 hrv_rmssd_milli, resting_heart_rate, spo2_percentage,
                 skin_temp_celsius, strain, daily_energy_kcal)
            VALUES (%s, %s, %s, 'oura', %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, readiness_id, *values),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_oura() -> None:
    init_db()
    user_id = get_local_user_id()

    last = get_last_synced_at(user_id, "oura")
    start_date = last.strftime("%Y-%m-%d") if last else None
    if start_date:
        print(f"Incremental sync from {start_date}")

    api_key, _ = get_integration_tokens(user_id, "oura")
    with OuraClient(api_key=api_key) as client:
        print("Fetching sleep…")
        sleeps = list(client.iter_sleep(start_date=start_date))
        print(f"  {len(sleeps)} sleep records found")

        print("Fetching readiness…")
        readiness_records = list(client.iter_readiness(start_date=start_date))
        print(f"  {len(readiness_records)} readiness records found")

    with get_connection() as conn:
        for record in sleeps:
            _upsert_sleep(conn, record, user_id)
        conn.commit()
        print(f"Sleep synced: {len(sleeps)} rows")

        for record in readiness_records:
            _upsert_readiness(conn, record, user_id)
        conn.commit()
        print(f"Readiness synced: {len(readiness_records)} rows")

    update_last_synced_at(user_id, "oura")
    print("Oura sync complete.")


if __name__ == "__main__":
    sync_oura()
