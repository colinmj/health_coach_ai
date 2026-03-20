"""Sync Whoop recovery and sleep data into PostgreSQL.

Run:
    python -m sync.whoop

Each run is idempotent. Requires WHOOP_ACCESS_TOKEN and WHOOP_REFRESH_TOKEN
in .env — run `python -m sync.whoop_auth` first if they are missing.
"""

import os

import psycopg
from dotenv import load_dotenv

from clients.whoop import WhoopClient
from db.schema import get_connection, get_local_user_id, init_db

load_dotenv()


# ---------------------------------------------------------------------------
# DB helpers — recovery
# ---------------------------------------------------------------------------

def _upsert_recovery(conn: psycopg.Connection, cycle: dict, user_id: int) -> None:
    """Insert or update a recovery row from a recovery record."""
    cycle_id = str(cycle["cycle_id"])
    recovery = cycle.get("score") or {}

    # Date: use created_at, truncated to calendar day
    created_at = cycle.get("created_at", "")
    date = created_at[:10]  # YYYY-MM-DD

    score_state = cycle.get("score_state")

    existing = conn.execute(
        "SELECT id FROM recovery WHERE whoop_cycle_id = %s AND user_id = %s",
        (cycle_id, user_id),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE recovery
            SET date=%s, score_state=%s, recovery_score=%s, hrv_rmssd_milli=%s,
                resting_heart_rate=%s, spo2_percentage=%s, skin_temp_celsius=%s
            WHERE whoop_cycle_id=%s AND user_id=%s
            """,
            (
                date,
                score_state,
                recovery.get("recovery_score"),
                recovery.get("hrv_rmssd_milli"),
                recovery.get("resting_heart_rate"),
                recovery.get("spo2_percentage"),
                recovery.get("skin_temp_celsius"),
                cycle_id,
                user_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO recovery
                (user_id, whoop_cycle_id, date, score_state, recovery_score, hrv_rmssd_milli,
                 resting_heart_rate, spo2_percentage, skin_temp_celsius)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                cycle_id,
                date,
                score_state,
                recovery.get("recovery_score"),
                recovery.get("hrv_rmssd_milli"),
                recovery.get("resting_heart_rate"),
                recovery.get("spo2_percentage"),
                recovery.get("skin_temp_celsius"),
            ),
        )


# ---------------------------------------------------------------------------
# DB helpers — sleep
# ---------------------------------------------------------------------------

def _upsert_sleep(conn: psycopg.Connection, record: dict, user_id: int) -> None:
    """Insert or update a sleep row."""
    sleep_id = str(record["id"])
    score = record.get("score") or {}
    stage = score.get("stage_summary") or {}

    start = record.get("start", "")
    date = start[:10]  # YYYY-MM-DD

    existing = conn.execute(
        "SELECT id FROM sleep WHERE whoop_sleep_id = %s AND user_id = %s",
        (sleep_id, user_id),
    ).fetchone()

    values = (
        date,
        str(record.get("cycle_id", "")),
        bool(record.get("nap")),
        record.get("score_state"),
        start,
        record.get("end"),
        stage.get("total_in_bed_time_milli"),
        stage.get("total_awake_time_milli"),
        stage.get("total_light_sleep_milli"),
        stage.get("total_slow_wave_sleep_milli"),
        stage.get("total_rem_sleep_milli"),
        stage.get("disturbance_count"),
        score.get("sleep_performance_percentage"),
        score.get("sleep_efficiency_percentage"),
        score.get("respiratory_rate"),
    )

    if existing:
        conn.execute(
            """
            UPDATE sleep
            SET date=%s, whoop_cycle_id=%s, is_nap=%s, score_state=%s,
                start_time=%s, end_time=%s, total_in_bed_time_milli=%s,
                total_awake_time_milli=%s, total_light_sleep_milli=%s,
                total_slow_wave_sleep_milli=%s, total_rem_sleep_milli=%s,
                disturbance_count=%s, sleep_performance_percentage=%s,
                sleep_efficiency_percentage=%s, respiratory_rate=%s
            WHERE whoop_sleep_id=%s AND user_id=%s
            """,
            (*values, sleep_id, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO sleep
                (user_id, date, whoop_cycle_id, is_nap, score_state, start_time, end_time,
                 total_in_bed_time_milli, total_awake_time_milli, total_light_sleep_milli,
                 total_slow_wave_sleep_milli, total_rem_sleep_milli, disturbance_count,
                 sleep_performance_percentage, sleep_efficiency_percentage,
                 respiratory_rate, whoop_sleep_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, *values, sleep_id),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_whoop() -> None:
    init_db()
    user_id = get_local_user_id()

    with WhoopClient(
        client_id=os.environ["WHOOP_CLIENT_ID"],
        client_secret=os.environ["WHOOP_CLIENT_SECRET"],
        access_token=os.environ["WHOOP_ACCESS_TOKEN"],
        refresh_token=os.environ["WHOOP_REFRESH_TOKEN"],
    ) as client:
        print("Fetching recovery…")
        cycles = list(client.iter_recovery())
        print(f"  {len(cycles)} recovery records found")

        print("Fetching sleep…")
        sleeps = list(client.iter_sleep())
        print(f"  {len(sleeps)} sleep records found")

    with get_connection() as conn:
        for cycle in cycles:
            _upsert_recovery(conn, cycle, user_id)
        conn.commit()
        print(f"Recovery synced: {len(cycles)} rows")

        for record in sleeps:
            _upsert_sleep(conn, record, user_id)
        conn.commit()
        print(f"Sleep synced: {len(sleeps)} rows")

    print("Whoop sync complete.")


if __name__ == "__main__":
    sync_whoop()
