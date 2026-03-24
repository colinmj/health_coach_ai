"""Sync Whoop recovery, sleep, and activity data into PostgreSQL.

Run:
    python -m sync.whoop

Each run is idempotent. Requires WHOOP_ACCESS_TOKEN and WHOOP_REFRESH_TOKEN
in .env — run `python -m sync.whoop_auth` first if they are missing.
"""

import os
from typing import Any

import psycopg
from dotenv import load_dotenv

from clients.whoop import WhoopClient
from db.schema import get_connection, get_local_user_id, init_db
from sync.utils import get_integration_tokens, get_last_synced_at, save_integration_tokens, update_last_synced_at

load_dotenv()


# ---------------------------------------------------------------------------
# DB helpers — recovery
# ---------------------------------------------------------------------------

def _upsert_recovery(conn: psycopg.Connection[dict[str, Any]], cycle: dict, user_id: int, strain: float | None, daily_energy_kcal: float | None = None) -> None:
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
                resting_heart_rate=%s, spo2_percentage=%s, skin_temp_celsius=%s,
                strain=%s, daily_energy_kcal=%s
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
                strain,
                daily_energy_kcal,
                cycle_id,
                user_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO recovery
                (user_id, whoop_cycle_id, date, score_state, recovery_score, hrv_rmssd_milli,
                 resting_heart_rate, spo2_percentage, skin_temp_celsius, strain, daily_energy_kcal)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                strain,
                daily_energy_kcal,
            ),
        )


# ---------------------------------------------------------------------------
# DB helpers — sleep
# ---------------------------------------------------------------------------

def _upsert_sleep(conn: psycopg.Connection[dict[str, Any]], record: dict, user_id: int) -> None:
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
        stage.get("total_light_sleep_time_milli"),
        stage.get("total_slow_wave_sleep_time_milli"),
        stage.get("total_rem_sleep_time_milli"),
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
# DB helpers — activities
# ---------------------------------------------------------------------------

def _upsert_activity(conn: psycopg.Connection[dict[str, Any]], record: dict, user_id: int) -> None:
    """Insert or update a whoop_activities row from a workout record."""
    workout_id = str(record["id"])
    score = record.get("score") or {}
    zones = score.get("zone_duration") or {}

    start = record.get("start", "")
    date = start[:10]  # YYYY-MM-DD

    sport_id = record.get("sport_id")
    sport_name = record.get("sport_name")
    kilojoules = score.get("kilojoule")
    energy_kcal = kilojoules / 4.184 if kilojoules is not None else None

    existing = conn.execute(
        "SELECT id FROM whoop_activities WHERE whoop_workout_id = %s AND user_id = %s",
        (workout_id, user_id),
    ).fetchone()

    values = (
        str(record.get("cycle_id", "")),
        date,
        sport_id,
        sport_name,
        record.get("score_state"),
        start,
        record.get("end"),
        score.get("strain"),
        energy_kcal,
        score.get("average_heart_rate"),
        score.get("max_heart_rate"),
        zones.get("zone_zero_milli"),
        zones.get("zone_one_milli"),
        zones.get("zone_two_milli"),
        zones.get("zone_three_milli"),
        zones.get("zone_four_milli"),
        zones.get("zone_five_milli"),
    )

    if existing:
        conn.execute(
            """
            UPDATE whoop_activities
            SET whoop_cycle_id=%s, date=%s, sport_id=%s, sport_name=%s, score_state=%s,
                start_time=%s, end_time=%s, strain=%s, energy_kcal=%s,
                avg_heart_rate=%s, max_heart_rate=%s,
                zone_zero_milli=%s, zone_one_milli=%s, zone_two_milli=%s,
                zone_three_milli=%s, zone_four_milli=%s, zone_five_milli=%s
            WHERE whoop_workout_id=%s AND user_id=%s
            """,
            (*values, workout_id, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO whoop_activities
                (user_id, whoop_workout_id, whoop_cycle_id, date, sport_id, sport_name,
                 score_state, start_time, end_time, strain, energy_kcal,
                 avg_heart_rate, max_heart_rate,
                 zone_zero_milli, zone_one_milli, zone_two_milli,
                 zone_three_milli, zone_four_milli, zone_five_milli)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, workout_id, *values),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_whoop() -> None:
    init_db()
    user_id = get_local_user_id()

    # Only fetch records newer than the last successful sync
    last = get_last_synced_at(user_id, "recovery")
    since = last.isoformat() if last else None
    if since:
        print(f"Incremental sync from {since}")

    access_token, refresh_token = get_integration_tokens(user_id, "whoop")
    with WhoopClient(
        client_id=os.environ["WHOOP_CLIENT_ID"],
        client_secret=os.environ["WHOOP_CLIENT_SECRET"],
        access_token=access_token,
        refresh_token=refresh_token,
        on_token_refresh=lambda at, rt: save_integration_tokens(user_id, "whoop", at, rt),
    ) as client:
        print("Fetching cycles (for strain)…")
        cycles = list(client.iter_cycles(start=since))
        strain_by_cycle: dict[str, float | None] = {}
        kcal_by_cycle: dict[str, float | None] = {}
        for c in cycles:
            cid = str(c["id"])
            score = c.get("score") or {}
            strain_by_cycle[cid] = score.get("strain")
            kj = score.get("kilojoule")
            kcal_by_cycle[cid] = kj / 4.184 if kj is not None else None
        print(f"  {len(cycles)} cycles found")

        print("Fetching recovery…")
        recovery_records = list(client.iter_recovery(start=since))
        print(f"  {len(recovery_records)} recovery records found")

        print("Fetching sleep…")
        sleeps = list(client.iter_sleep(start=since))
        print(f"  {len(sleeps)} sleep records found")

        print("Fetching activities…")
        workouts = list(client.iter_workouts(start=since))
        print(f"  {len(workouts)} activity records found")

    with get_connection() as conn:
        for record in recovery_records:
            cycle_id = str(record.get("cycle_id", ""))
            strain = strain_by_cycle.get(cycle_id)
            daily_energy_kcal = kcal_by_cycle.get(cycle_id)
            _upsert_recovery(conn, record, user_id, strain, daily_energy_kcal)
        conn.commit()
        print(f"Recovery synced: {len(recovery_records)} rows")

        for record in sleeps:
            _upsert_sleep(conn, record, user_id)
        conn.commit()
        print(f"Sleep synced: {len(sleeps)} rows")

        for record in workouts:
            _upsert_activity(conn, record, user_id)
        conn.commit()
        print(f"Activities synced: {len(workouts)} rows")

    update_last_synced_at(user_id, "recovery", "whoop")
    print("Whoop sync complete.")


if __name__ == "__main__":
    sync_whoop()
