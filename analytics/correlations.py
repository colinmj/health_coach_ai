import datetime

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
    """Pairs each workout's performance score with same-day nutrition data.
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
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
    """Pairs daily protein intake with average session 1RM on the same day.
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
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
    """Pairs prior-day nutrition with next-day recovery score.
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
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


def get_nutrition_vs_activity(
    sport_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs prior-night nutrition with activity performance metrics (HR, strain, calories).

    Designed for questions like 'how does carb intake the night before affect my max heart rate
    when I play hockey?'. sport_name is matched case-insensitively.
    Returns one row per activity session that has nutrition data for the prior day.
    """
    conditions = ["a.score_state = 'SCORED'"]
    params: list = []
    if sport_name is not None:
        conditions.append("a.sport_name ILIKE %s")
        params.append(f"%{sport_name}%")
    if since is not None:
        conditions.append("a.date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("a.date <= %s")
        params.append(until)

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT
            a.date               AS activity_date,
            a.sport_name,
            a.strain,
            a.avg_heart_rate,
            a.max_heart_rate,
            a.energy_kcal        AS calories_burned,
            n.energy_kcal        AS prior_night_energy_kcal,
            n.carbs_g            AS prior_night_carbs_g,
            n.net_carbs_g        AS prior_night_net_carbs_g,
            n.protein_g          AS prior_night_protein_g,
            n.fat_g              AS prior_night_fat_g,
            n.sugars_g           AS prior_night_sugars_g
        FROM activities a
        JOIN nutrition_daily n ON n.date = a.date - INTERVAL '1 day'
        {where}
        ORDER BY a.date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_activity_vs_strength(
    sport_name: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Pairs each Hevy workout with any Whoop activity logged the prior day.

    Designed for questions like 'do my lifts suffer the day after running?'
    sport_name is matched case-insensitively. Leave None to include all sports.
    Returns one row per (workout, prior-day activity) pair.
    """
    conditions = ["a.score_state = 'SCORED'"]
    params: list = []
    if sport_name is not None:
        conditions.append("a.sport_name ILIKE %s")
        params.append(f"%{sport_name}%")
    if since is not None:
        conditions.append("vp.workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("vp.workout_date <= %s")
        params.append(until)

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT
            vp.workout_date,
            vp.workout_title,
            vp.performance_score,
            vp.best_tag,
            vp.total_sets,
            a.sport_name          AS prior_day_sport,
            a.strain              AS prior_day_strain,
            a.avg_heart_rate      AS prior_day_avg_hr,
            a.max_heart_rate      AS prior_day_max_hr,
            a.energy_kcal         AS prior_day_calories
        FROM v_workout_performance vp
        JOIN activities a ON a.date = vp.workout_date - INTERVAL '1 day'
        {where}
        ORDER BY vp.workout_date
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_nutrition_vs_body_composition(
    since: str | None = None,
    until: str | None = None,
    days_window: int = 7,
) -> list[dict]:
    """For each nutrition day, finds the nearest body measurement within days_window days.
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
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


def get_energy_balance_vs_weight(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Daily energy balance (calories consumed minus Whoop daily burn) paired with
    rolling weight trend.

    Returns one row per day where both nutrition and a scored Whoop recovery record
    exist. Rolling 7-day averages smooth out day-to-day noise. The expected weight
    change column applies the 7700 kcal/kg rule to the rolling balance so the agent
    can compare it against the actual weight delta — exposing tracking errors or
    Whoop inaccuracy when the two diverge significantly.
    """
    conditions = ["n.user_id = %s", "n.energy_kcal IS NOT NULL", "r.daily_energy_kcal IS NOT NULL"]
    params: list = []

    # user_id appears three times: once in the main WHERE and twice in the LATERAL joins
    # We build the date filters separately so we can apply them to the CTE
    date_conditions = []
    if since is not None:
        date_conditions.append("n.date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("n.date <= %s")
        params.append(until)

    all_conditions = conditions + date_conditions
    where = "WHERE " + " AND ".join(all_conditions)

    sql = f"""
        WITH daily_balance AS (
            SELECT
                n.date,
                n.energy_kcal                              AS calories_consumed,
                r.daily_energy_kcal                        AS calories_burned,
                n.energy_kcal - r.daily_energy_kcal        AS daily_balance
            FROM nutrition_daily n
            JOIN recovery r
              ON r.date = n.date
             AND r.user_id = n.user_id
             AND r.score_state = 'SCORED'
            {where}
            ORDER BY n.date
        ),
        rolling AS (
            SELECT
                date,
                ROUND(calories_consumed::numeric, 1)                                        AS calories_consumed,
                ROUND(calories_burned::numeric, 1)                                          AS calories_burned,
                ROUND(daily_balance::numeric, 1)                                            AS daily_balance,
                ROUND(AVG(calories_consumed) OVER w7::numeric, 1)                          AS rolling_7d_avg_consumed,
                ROUND(AVG(calories_burned)   OVER w7::numeric, 1)                          AS rolling_7d_avg_burned,
                ROUND(AVG(daily_balance)     OVER w7::numeric, 1)                          AS rolling_7d_avg_balance,
                ROUND((AVG(daily_balance) OVER w7 * 7.0 / 7700.0)::numeric, 3)            AS rolling_7d_expected_weight_change_kg
            FROM daily_balance
            WINDOW w7 AS (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
        )
        SELECT
            r.date,
            r.calories_consumed,
            r.calories_burned,
            r.daily_balance,
            r.rolling_7d_avg_consumed,
            r.rolling_7d_avg_burned,
            r.rolling_7d_avg_balance,
            r.rolling_7d_expected_weight_change_kg,
            w_now.weight_kg,
            w_ago.weight_kg                                                                 AS weight_7d_ago_kg,
            ROUND((w_now.weight_kg - w_ago.weight_kg)::numeric, 2)                        AS actual_7d_weight_change_kg
        FROM rolling r
        LEFT JOIN LATERAL (
            SELECT weight_kg FROM body_measurements
            WHERE user_id = %s AND date <= r.date
            ORDER BY date DESC LIMIT 1
        ) w_now ON TRUE
        LEFT JOIN LATERAL (
            SELECT weight_kg FROM body_measurements
            WHERE user_id = %s AND date <= r.date - INTERVAL '7 days'
            ORDER BY date DESC LIMIT 1
        ) w_ago ON TRUE
        ORDER BY r.date
    """
    # Append user_id twice for the LATERAL subqueries
    with get_connection() as conn:
        rows = conn.execute(sql, [user_id] + params + [user_id, user_id]).fetchall()
    return [dict(row) for row in rows]
