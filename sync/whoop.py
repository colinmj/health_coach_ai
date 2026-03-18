"""Sync Whoop recovery and sleep data into SQLite.

Run:
    python -m sync.whoop

Each run is idempotent. Requires WHOOP_ACCESS_TOKEN and WHOOP_REFRESH_TOKEN
in .env — run `python -m sync.whoop_auth` first if they are missing.
"""

import os
import sqlite3

from dotenv import load_dotenv

from clients.whoop import WhoopClient
from db.schema import get_connection, init_db

load_dotenv()


# ---------------------------------------------------------------------------
# DB helpers — recovery
# ---------------------------------------------------------------------------

def _upsert_recovery(conn: sqlite3.Connection, cycle: dict) -> None:
    """Insert or update a recovery row from a cycle record."""
    cycle_id = str(cycle["id"])
    recovery = cycle.get("score") or {}

    # Date: use the cycle start time, truncated to calendar day
    start = cycle.get("start", "")
    date = start[:10]  # YYYY-MM-DD

    score_state = cycle.get("score_state")

    existing = conn.execute(
        "SELECT id FROM recovery WHERE whoop_cycle_id = ?", (cycle_id,)
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE recovery
            SET date=?, score_state=?, recovery_score=?, hrv_rmssd_milli=?,
                resting_heart_rate=?, spo2_percentage=?, skin_temp_celsius=?
            WHERE whoop_cycle_id=?
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
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO recovery
                (whoop_cycle_id, date, score_state, recovery_score, hrv_rmssd_milli,
                 resting_heart_rate, spo2_percentage, skin_temp_celsius)
            VALUES (?,?,?,?,?,?,?,?)
            """,
            (
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

def _upsert_sleep(conn: sqlite3.Connection, record: dict) -> None:
    """Insert or update a sleep row."""
    sleep_id = str(record["id"])
    score = record.get("score") or {}
    stage = score.get("stage_summary") or {}

    start = record.get("start", "")
    date = start[:10]  # YYYY-MM-DD

    existing = conn.execute(
        "SELECT id FROM sleep WHERE whoop_sleep_id = ?", (sleep_id,)
    ).fetchone()

    values = (
        date,
        str(record.get("cycle_id", "")),
        1 if record.get("nap") else 0,
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
            SET date=?, whoop_cycle_id=?, is_nap=?, score_state=?,
                start_time=?, end_time=?, total_in_bed_time_milli=?,
                total_awake_time_milli=?, total_light_sleep_milli=?,
                total_slow_wave_sleep_milli=?, total_rem_sleep_milli=?,
                disturbance_count=?, sleep_performance_percentage=?,
                sleep_efficiency_percentage=?, respiratory_rate=?
            WHERE whoop_sleep_id=?
            """,
            (*values, sleep_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO sleep
                (date, whoop_cycle_id, is_nap, score_state, start_time, end_time,
                 total_in_bed_time_milli, total_awake_time_milli, total_light_sleep_milli,
                 total_slow_wave_sleep_milli, total_rem_sleep_milli, disturbance_count,
                 sleep_performance_percentage, sleep_efficiency_percentage,
                 respiratory_rate, whoop_sleep_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (*values, sleep_id),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_whoop() -> None:
    init_db()

    with WhoopClient(
        client_id=os.environ["WHOOP_CLIENT_ID"],
        client_secret=os.environ["WHOOP_CLIENT_SECRET"],
        access_token=os.environ["WHOOP_ACCESS_TOKEN"],
        refresh_token=os.environ["WHOOP_REFRESH_TOKEN"],
    ) as client:
        print("Fetching recovery (cycles)…")
        cycles = list(client.iter_cycles())
        print(f"  {len(cycles)} cycles found")

        print("Fetching sleep…")
        sleeps = list(client.iter_sleep())
        print(f"  {len(sleeps)} sleep records found")

    with get_connection() as conn:
        for cycle in cycles:
            _upsert_recovery(conn, cycle)
        conn.commit()
        print(f"Recovery synced: {len(cycles)} rows")

        for record in sleeps:
            _upsert_sleep(conn, record)
        conn.commit()
        print(f"Sleep synced: {len(sleeps)} rows")

    print("Whoop sync complete.")


if __name__ == "__main__":
    sync_whoop()
