from db.schema import get_connection


def get_activities(
    sport_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Activity sessions from Whoop, optionally filtered by sport and date range.

    sport_name is matched case-insensitively (e.g. 'hockey' matches 'Ice Hockey').
    Returns strain, HR, calories, and HR zone breakdown per session.
    """
    conditions = ["score_state = 'SCORED'"]
    params: list = []
    if sport_name is not None:
        conditions.append("sport_name ILIKE %s")
        params.append(f"%{sport_name}%")
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT date, sport_id, sport_name, start_time, end_time,
               strain, energy_kcal, avg_heart_rate, max_heart_rate,
               zone_zero_milli, zone_one_milli, zone_two_milli,
               zone_three_milli, zone_four_milli, zone_five_milli
        FROM whoop_activities
        {where}
        ORDER BY date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_activity_sports(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Distinct sports logged by the user with session counts and date range.

    Use this to discover what activities are available before querying get_activities.
    """
    conditions = ["score_state = 'SCORED'"]
    params: list = []
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT
            sport_name,
            COUNT(*) AS session_count,
            MIN(date) AS first_session,
            MAX(date) AS last_session,
            ROUND(AVG(strain)::numeric, 1) AS avg_strain,
            ROUND(AVG(energy_kcal)::numeric, 0) AS avg_energy_kcal
        FROM whoop_activities
        {where}
        GROUP BY sport_name
        ORDER BY session_count DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_recovery(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Recovery scores and HRV data, optionally filtered by date range (YYYY-MM-DD)."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)
    sql = """
        SELECT date, recovery_score, hrv_rmssd_milli, resting_heart_rate,
               spo2_percentage, skin_temp_celsius, strain, daily_energy_kcal
        FROM recovery
        WHERE score_state = 'SCORED'
    """
    if conditions:
        sql += " AND " + " AND ".join(conditions)
    sql += " ORDER BY date"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_sleep(
    since: str | None = None,
    until: str | None = None,
    exclude_naps: bool = True,
) -> list[dict]:
    """Sleep performance and architecture data, optionally filtered by date range (YYYY-MM-DD)."""
    conditions = []
    params: list = []
    if exclude_naps:
        conditions.append("is_nap = FALSE")
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)
    sql = """
        SELECT date, sleep_performance_percentage, sleep_efficiency_percentage,
               total_rem_sleep_milli, total_slow_wave_sleep_milli,
               total_in_bed_time_milli, respiratory_rate
        FROM sleep
        WHERE score_state = 'SCORED'
    """
    if conditions:
        sql += " AND " + " AND ".join(conditions)
    sql += " ORDER BY date"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
