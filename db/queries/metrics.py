"""Raw metric fetchers used by analytics/compliance.py.

Each function takes (conn, user_id, week_start, week_end) and returns the
raw value or None (nutrition) / 0.0 (frequency counters).
"""


def fetch_nutrition_metric(conn, user_id, column: str, week_start, week_end) -> float | None:
    """AVG of a nutrition_daily column over the week window.

    column must be pre-validated against _NUTRITION_METRICS in compliance.py
    before calling this function.
    """
    row = conn.execute(
        f"SELECT AVG({column}) AS val FROM nutrition_daily "
        "WHERE user_id = %s AND date >= %s AND date < %s",
        (user_id, week_start, week_end),
    ).fetchone()
    return row["val"] if row else None


def fetch_workout_frequency(conn, user_id, week_start, week_end) -> float:
    row = conn.execute(
        "SELECT COUNT(DISTINCT start_time::date) AS val FROM hevy_workouts "
        "WHERE user_id = %s AND start_time::date >= %s AND start_time::date < %s",
        (user_id, week_start, week_end),
    ).fetchone()
    return float(row["val"]) if row and row["val"] is not None else 0.0


def fetch_activity_frequency(conn, user_id, week_start, week_end) -> float:
    row = conn.execute(
        "SELECT COUNT(*) AS val FROM whoop_activities "
        "WHERE user_id = %s AND date >= %s AND date < %s",
        (user_id, week_start, week_end),
    ).fetchone()
    return float(row["val"]) if row and row["val"] is not None else 0.0


def fetch_running_frequency(conn, user_id, week_start, week_end) -> float:
    row = conn.execute(
        "SELECT COUNT(*) AS val FROM whoop_activities "
        "WHERE user_id = %s AND date >= %s AND date < %s AND sport_name ILIKE '%running%'",
        (user_id, week_start, week_end),
    ).fetchone()
    return float(row["val"]) if row and row["val"] is not None else 0.0
