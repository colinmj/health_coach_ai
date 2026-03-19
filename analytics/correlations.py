from db.schema import get_connection


def get_hrv_vs_performance(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs each workout's performance score with the prior night's recovery/HRV data."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("vp.workout_date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= ?")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            vp.workout_date,
            vp.workout_title,
            vp.performance_score,
            vp.best_tag,
            vp.total_sets,
            r.recovery_score   AS prior_night_recovery_score,
            r.hrv_rmssd_milli  AS prior_night_hrv_milli,
            r.resting_heart_rate AS prior_night_rhr
        FROM v_workout_performance vp
        JOIN recovery r ON r.date = DATE(vp.workout_date, '-1 day')
        {where}
        ORDER BY vp.workout_date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_sleep_vs_performance(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs each workout's performance score with the prior night's sleep data (ms → minutes)."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("vp.workout_date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= ?")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            vp.workout_date,
            vp.workout_title,
            vp.performance_score,
            vp.best_tag,
            sl.sleep_performance_percentage  AS prior_night_sleep_performance,
            sl.sleep_efficiency_percentage   AS prior_night_sleep_efficiency,
            ROUND(sl.total_slow_wave_sleep_milli / 60000.0, 1) AS prior_night_sws_minutes,
            ROUND(sl.total_rem_sleep_milli       / 60000.0, 1) AS prior_night_rem_minutes,
            ROUND(sl.total_in_bed_time_milli     / 60000.0, 1) AS prior_night_in_bed_minutes
        FROM v_workout_performance vp
        JOIN sleep sl ON sl.date = DATE(vp.workout_date, '-1 day')
                      AND sl.is_nap = 0
                      AND sl.score_state = 'SCORED'
        {where}
        ORDER BY vp.workout_date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_sleep_threshold_vs_performance(
    threshold_hours: float = 7.0,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Compares avg workout performance for nights above vs below a sleep duration threshold.

    Returns two rows — one for each group — so the agent can narrate the difference
    without computing statistics itself.
    """
    threshold_milli = int(threshold_hours * 3_600_000)
    conditions = ["vp.workout_date >= ?", "vp.workout_date <= ?"] if False else []
    params: list = [threshold_milli, threshold_milli]
    date_conditions = []
    if since is not None:
        date_conditions.append("vp.workout_date >= ?")
        params.append(since)
    if until is not None:
        date_conditions.append("vp.workout_date <= ?")
        params.append(until)

    where = ("AND " + " AND ".join(date_conditions)) if date_conditions else ""

    sql = f"""
        WITH paired AS (
            SELECT
                vp.performance_score,
                vp.best_tag,
                sl.total_in_bed_time_milli,
                CASE
                    WHEN sl.total_in_bed_time_milli >= ? THEN 'above_threshold'
                    ELSE 'below_threshold'
                END AS sleep_group
            FROM v_workout_performance vp
            JOIN sleep sl ON sl.date = DATE(vp.workout_date, '-1 day')
                          AND sl.is_nap = 0
                          AND sl.score_state = 'SCORED'
            WHERE sl.total_in_bed_time_milli IS NOT NULL
              {where}
        )
        SELECT
            sleep_group,
            ROUND(? / 3600000.0, 1)           AS threshold_hours,
            COUNT(*)                           AS workout_count,
            ROUND(AVG(performance_score), 2)   AS avg_performance_score,
            ROUND(AVG(total_in_bed_time_milli) / 60000.0, 1) AS avg_sleep_minutes,
            SUM(CASE WHEN best_tag = 'PR'     THEN 1 ELSE 0 END) AS pr_workouts,
            SUM(CASE WHEN best_tag = 'Better' THEN 1 ELSE 0 END) AS better_workouts,
            SUM(CASE WHEN best_tag = 'Worse'  THEN 1 ELSE 0 END) AS worse_workouts
        FROM paired
        GROUP BY sleep_group
        ORDER BY sleep_group DESC
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_body_composition_vs_strength(
    since: str | None = None,
    until: str | None = None,
    days_window: int = 7,
) -> list[dict]:
    """For each body measurement, finds the nearest workout within days_window days
    and returns average 1RM across exercises in that workout."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("bm.date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("bm.date <= ?")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # days_window is an int so safe to interpolate directly
    sql = f"""
        WITH nearest_workout AS (
            SELECT
                bm.id AS bm_id,
                w.hevy_id AS workout_hevy_id,
                DATE(w.start_time) AS workout_date,
                ABS(JULIANDAY(DATE(w.start_time)) - JULIANDAY(bm.date)) AS day_diff,
                ROW_NUMBER() OVER (
                    PARTITION BY bm.id
                    ORDER BY ABS(JULIANDAY(DATE(w.start_time)) - JULIANDAY(bm.date))
                ) AS rn
            FROM body_measurements bm
            JOIN hevy_workouts w ON ABS(JULIANDAY(DATE(w.start_time)) - JULIANDAY(bm.date)) <= {days_window}
        ),
        workout_avg_1rm AS (
            SELECT
                nw.bm_id,
                nw.workout_date AS nearest_workout_date,
                ROUND(AVG(v1.session_best_1rm_kg), 2) AS avg_1rm_kg_across_exercises,
                COUNT(DISTINCT v1.exercise_template_id) AS exercises_tracked
            FROM nearest_workout nw
            JOIN v_workout_1rm v1 ON DATE(v1.workout_date) = nw.workout_date
            WHERE nw.rn = 1
            GROUP BY nw.bm_id, nw.workout_date
        )
        SELECT
            bm.date              AS measurement_date,
            bm.weight_kg,
            bm.fat_ratio,
            bm.muscle_mass_kg,
            bm.fat_free_mass_kg,
            wa.nearest_workout_date,
            wa.avg_1rm_kg_across_exercises,
            wa.exercises_tracked
        FROM body_measurements bm
        JOIN workout_avg_1rm wa ON wa.bm_id = bm.id
        {where}
        ORDER BY bm.date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
