from db.schema import get_connection


def get_performance_drivers(
    user_id: int,
    conn,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Fetch a combined dataset of workout performance paired with prior-day
    sleep, recovery, and nutrition predictors in a single query.

    Returns one row per workout. LEFT JOINs mean predictor columns may be NULL
    where a domain has no data for that date; the regression service filters these.

    Each dict has keys:
        workout_date, performance_score, total_sets,
        hrv_rmssd_milli, recovery_score, resting_heart_rate,
        sleep_minutes, sleep_efficiency,
        protein_g, carbs_g, energy_kcal
    """
    # Placeholder order matches appearance in SQL:
    # 1: recovery JOIN user_id, 2: sleep JOIN user_id, 3: nutrition JOIN user_id,
    # 4: WHERE vp.user_id, 5+: optional since/until
    params: list = [user_id, user_id, user_id, user_id]

    date_conditions = []
    if since:
        date_conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until:
        date_conditions.append("vp.workout_date <= %s")
        params.append(until)

    extra_where = (" AND " + " AND ".join(date_conditions)) if date_conditions else ""

    sql = f"""
        SELECT
            vp.workout_date,
            vp.performance_score,
            vp.total_sets,
            r.hrv_rmssd_milli                                           AS hrv_rmssd_milli,
            r.recovery_score                                            AS recovery_score,
            r.resting_heart_rate                                        AS resting_heart_rate,
            ROUND((s.total_in_bed_time_milli / 60000.0)::numeric, 1)   AS sleep_minutes,
            s.sleep_efficiency_percentage                               AS sleep_efficiency,
            n.protein_g                                                 AS protein_g,
            n.carbs_g                                                   AS carbs_g,
            n.energy_kcal                                               AS energy_kcal
        FROM v_workout_performance vp
        LEFT JOIN recovery r
            ON r.user_id = %s
            AND r.date = vp.workout_date - INTERVAL '1 day'
        LEFT JOIN sleep s
            ON s.user_id = %s
            AND s.date = vp.workout_date - INTERVAL '1 day'
            AND s.is_nap = FALSE
            AND s.score_state = 'SCORED'
        LEFT JOIN nutrition_daily n
            ON n.user_id = %s
            AND n.date = vp.workout_date - INTERVAL '1 day'
        WHERE vp.user_id = %s{extra_where}
        ORDER BY vp.workout_date
    """
    rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
