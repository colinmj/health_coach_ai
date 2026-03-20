from db.schema import get_connection


def get_hrv_vs_performance(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs each workout's performance score with the prior night's recovery/HRV data."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= %s")
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
        JOIN recovery r ON r.date = vp.workout_date - INTERVAL '1 day'
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
        conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= %s")
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
            ROUND((sl.total_slow_wave_sleep_milli / 60000.0)::numeric, 1) AS prior_night_sws_minutes,
            ROUND((sl.total_rem_sleep_milli       / 60000.0)::numeric, 1) AS prior_night_rem_minutes,
            ROUND((sl.total_in_bed_time_milli     / 60000.0)::numeric, 1) AS prior_night_in_bed_minutes
        FROM v_workout_performance vp
        JOIN sleep sl ON sl.date = vp.workout_date - INTERVAL '1 day'
                      AND sl.is_nap = FALSE
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
    params: list = [threshold_milli]
    date_conditions = []
    if since is not None:
        date_conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("vp.workout_date <= %s")
        params.append(until)
    params.append(threshold_milli)  # for ROUND in outer SELECT

    where = ("AND " + " AND ".join(date_conditions)) if date_conditions else ""

    sql = f"""
        WITH paired AS (
            SELECT
                vp.performance_score,
                vp.best_tag,
                sl.total_in_bed_time_milli,
                CASE
                    WHEN sl.total_in_bed_time_milli >= %s THEN 'above_threshold'
                    ELSE 'below_threshold'
                END AS sleep_group
            FROM v_workout_performance vp
            JOIN sleep sl ON sl.date = vp.workout_date - INTERVAL '1 day'
                          AND sl.is_nap = FALSE
                          AND sl.score_state = 'SCORED'
            WHERE sl.total_in_bed_time_milli IS NOT NULL
              {where}
        )
        SELECT
            sleep_group,
            ROUND((%s / 3600000.0)::numeric, 1)           AS threshold_hours,
            COUNT(*)                                        AS workout_count,
            ROUND(AVG(performance_score)::numeric, 2)       AS avg_performance_score,
            ROUND((AVG(total_in_bed_time_milli) / 60000.0)::numeric, 1) AS avg_sleep_minutes,
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
        conditions.append("bm.date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("bm.date <= %s")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # days_window is an int so safe to interpolate directly
    sql = f"""
        WITH nearest_workout AS (
            SELECT
                bm.id AS bm_id,
                w.hevy_id AS workout_hevy_id,
                w.start_time::date AS workout_date,
                ABS(w.start_time::date - bm.date) AS day_diff,
                ROW_NUMBER() OVER (
                    PARTITION BY bm.id
                    ORDER BY ABS(w.start_time::date - bm.date)
                ) AS rn
            FROM body_measurements bm
            JOIN hevy_workouts w ON ABS(w.start_time::date - bm.date) <= {days_window}
        ),
        workout_avg_1rm AS (
            SELECT
                nw.bm_id,
                nw.workout_date AS nearest_workout_date,
                ROUND(AVG(v1.session_best_1rm_kg)::numeric, 2) AS avg_1rm_kg_across_exercises,
                COUNT(DISTINCT v1.exercise_template_id) AS exercises_tracked
            FROM nearest_workout nw
            JOIN v_workout_1rm v1 ON v1.workout_date::date = nw.workout_date
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


def get_nutrition_vs_performance(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs each workout's performance score with same-day nutrition data."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= %s")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            vp.workout_date,
            vp.workout_title,
            vp.performance_score,
            vp.best_tag,
            n.energy_kcal,
            n.protein_g,
            n.carbs_g,
            n.net_carbs_g,
            n.fat_g,
            n.fiber_g
        FROM v_workout_performance vp
        JOIN nutrition_daily n ON n.date = vp.workout_date
        {where}
        ORDER BY vp.workout_date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_protein_vs_strength(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs daily protein intake with average session 1RM on the same day."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("n.date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("n.date <= %s")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            n.date,
            n.protein_g,
            n.energy_kcal,
            ROUND(AVG(v1.session_best_1rm_kg)::numeric, 2) AS avg_session_1rm_kg,
            COUNT(DISTINCT v1.exercise_template_id) AS exercise_count
        FROM nutrition_daily n
        JOIN v_workout_1rm v1 ON v1.workout_date::date = n.date
        {where}
        GROUP BY n.date, n.protein_g, n.energy_kcal
        ORDER BY n.date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_carbs_prior_to_prs(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """For each PR workout, returns carb totals for the 3 days leading up to it."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= %s")
        params.append(until)

    where = ("WHERE vp.best_tag = 'PR' AND " + " AND ".join(conditions)) if conditions else "WHERE vp.best_tag = 'PR'"

    sql = f"""
        SELECT
            vp.workout_date,
            vp.workout_title,
            vp.pr_sets,
            n1.carbs_g        AS carbs_day_minus_1,
            n1.net_carbs_g    AS net_carbs_day_minus_1,
            n2.carbs_g        AS carbs_day_minus_2,
            n2.net_carbs_g    AS net_carbs_day_minus_2,
            n3.carbs_g        AS carbs_day_minus_3,
            n3.net_carbs_g    AS net_carbs_day_minus_3,
            ROUND(((COALESCE(n1.carbs_g, 0) + COALESCE(n2.carbs_g, 0) + COALESCE(n3.carbs_g, 0))
                  / NULLIF(
                      (CASE WHEN n1.carbs_g IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN n2.carbs_g IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN n3.carbs_g IS NOT NULL THEN 1 ELSE 0 END), 0
                  ))::numeric, 1) AS avg_carbs_3d,
            ROUND(((COALESCE(n1.net_carbs_g, 0) + COALESCE(n2.net_carbs_g, 0) + COALESCE(n3.net_carbs_g, 0))
                  / NULLIF(
                      (CASE WHEN n1.net_carbs_g IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN n2.net_carbs_g IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN n3.net_carbs_g IS NOT NULL THEN 1 ELSE 0 END), 0
                  ))::numeric, 1) AS avg_net_carbs_3d
        FROM v_workout_performance vp
        LEFT JOIN nutrition_daily n1 ON n1.date = vp.workout_date - INTERVAL '1 day'
        LEFT JOIN nutrition_daily n2 ON n2.date = vp.workout_date - INTERVAL '2 days'
        LEFT JOIN nutrition_daily n3 ON n3.date = vp.workout_date - INTERVAL '3 days'
        {where}
        ORDER BY vp.workout_date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_nutrition_vs_recovery(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs prior-day nutrition with next-day recovery score."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("r.date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("r.date <= %s")
        params.append(until)

    where = ("WHERE r.score_state = 'SCORED' AND " + " AND ".join(conditions)) if conditions else "WHERE r.score_state = 'SCORED'"

    sql = f"""
        SELECT
            r.date                AS recovery_date,
            r.recovery_score,
            r.hrv_rmssd_milli,
            n.energy_kcal         AS prior_day_energy_kcal,
            n.protein_g           AS prior_day_protein_g,
            n.carbs_g             AS prior_day_carbs_g,
            n.fat_g               AS prior_day_fat_g
        FROM recovery r
        JOIN nutrition_daily n ON n.date = r.date - INTERVAL '1 day'
        {where}
        ORDER BY r.date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_nutrition_vs_body_composition(
    since: str | None = None,
    until: str | None = None,
    days_window: int = 7,
) -> list[dict]:
    """For each nutrition day, finds the nearest body measurement within days_window days."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("n.date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("n.date <= %s")
        params.append(until)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    # days_window is an int so safe to interpolate directly
    sql = f"""
        WITH nearest_measurement AS (
            SELECT
                n.date AS nutrition_date,
                bm.id AS bm_id,
                ABS(bm.date - n.date) AS day_diff,
                ROW_NUMBER() OVER (
                    PARTITION BY n.date
                    ORDER BY ABS(bm.date - n.date)
                ) AS rn
            FROM nutrition_daily n
            JOIN body_measurements bm
              ON ABS(bm.date - n.date) <= {days_window}
        )
        SELECT
            n.date,
            n.energy_kcal,
            n.protein_g,
            n.carbs_g,
            n.fat_g,
            bm.weight_kg,
            bm.fat_ratio,
            bm.muscle_mass_kg
        FROM nutrition_daily n
        JOIN nearest_measurement nm ON nm.nutrition_date = n.date AND nm.rn = 1
        JOIN body_measurements bm ON bm.id = nm.bm_id
        {where}
        ORDER BY n.date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
