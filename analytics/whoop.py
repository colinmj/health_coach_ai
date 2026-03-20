from db.schema import get_connection


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
               spo2_percentage, skin_temp_celsius
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
