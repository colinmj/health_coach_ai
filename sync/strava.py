"""Sync Strava activity data into PostgreSQL.

Run:
    python -m sync.strava

Each run is idempotent. Requires STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in
.env, plus OAuth tokens stored in user_integrations — go through the OAuth
flow in Settings first.
"""

import os
from typing import Any

import psycopg
from dotenv import load_dotenv

from clients.strava import StravaClient
from db.schema import get_connection, get_request_user_id, set_current_user_id, get_cli_user_id, init_db
from sync.activity_categories import classify_activity
from sync.utils import get_integration_tokens, get_last_synced_at, save_integration_tokens, update_last_synced_at

load_dotenv()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _upsert_activity(conn: psycopg.Connection[dict[str, Any]], activity: dict, user_id: int) -> None:
    activity_id = str(activity["id"])
    start_local = activity.get("start_date_local", "")
    date = start_local[:10]

    kilojoules = activity.get("kilojoules")
    energy_kcal = kilojoules / 4.184 if kilojoules is not None else None

    distance_m = activity.get("distance")  # Strava gives metres
    duration_s = activity.get("elapsed_time")  # seconds

    sport_name = activity.get("type")
    activity_category = classify_activity(sport_name, "strava")

    values = (
        date,
        sport_name,
        None,   # sport_id
        activity_category,
        None,   # score_state
        activity.get("start_date"),
        None,   # end_time — Strava doesn't return end_time directly
        duration_s,
        distance_m,
        None,   # strain
        energy_kcal,
        round(activity["average_heartrate"]) if activity.get("average_heartrate") else None,
        round(activity["max_heartrate"]) if activity.get("max_heartrate") else None,
        None, None, None, None, None, None,  # HR zones — not in summary activity
    )

    existing = conn.execute(
        "SELECT id FROM activities WHERE source = 'strava' AND external_id = %s AND user_id = %s",
        (activity_id, user_id),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE activities
            SET date=%s, sport_name=%s, sport_id=%s, activity_category=%s,
                score_state=%s, start_time=%s, end_time=%s, duration_seconds=%s,
                distance_meters=%s, strain=%s, energy_kcal=%s,
                avg_heart_rate=%s, max_heart_rate=%s,
                zone_zero_milli=%s, zone_one_milli=%s, zone_two_milli=%s,
                zone_three_milli=%s, zone_four_milli=%s, zone_five_milli=%s
            WHERE source='strava' AND external_id=%s AND user_id=%s
            """,
            (*values, activity_id, user_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO activities
                (user_id, source, external_id, date, sport_name, sport_id, activity_category,
                 score_state, start_time, end_time, duration_seconds, distance_meters,
                 strain, energy_kcal, avg_heart_rate, max_heart_rate,
                 zone_zero_milli, zone_one_milli, zone_two_milli,
                 zone_three_milli, zone_four_milli, zone_five_milli)
            VALUES (%s, 'strava', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, activity_id, *values),
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_strava() -> None:
    init_db()
    user_id = get_request_user_id()

    last = get_last_synced_at(user_id, "strava")
    if last:
        print(f"Incremental sync from {last.isoformat()}")

    access_token, refresh_token = get_integration_tokens(user_id, "strava")
    with StravaClient(
        client_id=os.environ["STRAVA_CLIENT_ID"],
        client_secret=os.environ["STRAVA_CLIENT_SECRET"],
        access_token=access_token,
        refresh_token=refresh_token,
        on_token_refresh=lambda at, rt: save_integration_tokens(user_id, "strava", at, rt),
    ) as client:
        print("Fetching activities…")
        activities = list(client.iter_activities(after=last))
        print(f"  {len(activities)} activities found")

    with get_connection() as conn:
        for activity in activities:
            _upsert_activity(conn, activity, user_id)
        conn.commit()
        print(f"Activities synced: {len(activities)} rows")

    update_last_synced_at(user_id, "strava")
    print("Strava sync complete.")


if __name__ == "__main__":
    set_current_user_id(get_cli_user_id())
    sync_strava()
