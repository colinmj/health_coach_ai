from db.schema import get_connection


def get_food_vs_performance(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """For each food item eaten on a workout day or the day before, counts how often
    that food appeared on days where the workout had at least one PR or Better set
    vs days where it did not.

    Aggregates across the window: food_name, category, meal_group, appearances on
    PR/Better days, appearances on non-PR days, and average macros contributed per
    appearance.

    Returns a list of dicts with keys:
        food_name, category, meal_group,
        appearances_on_pr_days, appearances_on_non_pr_days,
        avg_protein_g, avg_carbs_g, avg_fat_g, avg_energy_kcal
    """
    date_conditions = []
    params: list = [user_id]
    if since is not None:
        date_conditions.append("w.start_time::date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("w.start_time::date <= %s")
        params.append(until)

    date_where = (" AND " + " AND ".join(date_conditions)) if date_conditions else ""
    params.append(user_id)

    sql = f"""
        WITH workout_performance AS (
            SELECT
                w.start_time::date AS workout_date,
                CASE
                    WHEN MAX(CASE WHEN s.performance_tag IN ('PR', 'Better') THEN 1 ELSE 0 END) = 1
                    THEN TRUE
                    ELSE FALSE
                END AS had_pr_or_better
            FROM hevy_workouts w
            JOIN hevy_exercises e ON e.workout_id = w.id
            JOIN hevy_sets s      ON s.exercise_id = e.id
            WHERE w.user_id = %s
              AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
              {date_where}
            GROUP BY w.start_time::date
        ),
        food_workout_pairs AS (
            SELECT
                nf.food_name,
                nf.category,
                nf.meal_group,
                nf.energy_kcal,
                nf.protein_g,
                nf.carbs_g,
                nf.fat_g,
                wp.had_pr_or_better
            FROM nutrition_foods nf
            JOIN workout_performance wp
              ON wp.workout_date = nf.date
              OR wp.workout_date = nf.date + INTERVAL '1 day'
            WHERE nf.user_id = %s
        )
        SELECT
            food_name,
            category,
            meal_group,
            SUM(CASE WHEN had_pr_or_better THEN 1 ELSE 0 END)    AS appearances_on_pr_days,
            SUM(CASE WHEN NOT had_pr_or_better THEN 1 ELSE 0 END) AS appearances_on_non_pr_days,
            ROUND(AVG(protein_g)::numeric, 2)                     AS avg_protein_g,
            ROUND(AVG(carbs_g)::numeric, 2)                       AS avg_carbs_g,
            ROUND(AVG(fat_g)::numeric, 2)                         AS avg_fat_g,
            ROUND(AVG(energy_kcal)::numeric, 2)                   AS avg_energy_kcal
        FROM food_workout_pairs
        GROUP BY food_name, category, meal_group
        ORDER BY appearances_on_pr_days DESC, food_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_food_vs_sleep(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """For each evening food item (dinner/snack, or logged after 17:00), pairs it with
    the following night's sleep metrics.

    Sleep durations are returned in hours (converted from milliseconds). Sleep quality
    is represented by sleep_performance_percentage from the Whoop sleep table.

    Returns a list of dicts with keys:
        food_name, category, meal_group, date, sleep_date,
        total_in_bed_hours, sleep_performance_pct, sleep_efficiency_pct,
        slow_wave_sleep_hours, rem_sleep_hours,
        energy_kcal, protein_g, carbs_g, fat_g, fiber_g
    """
    conditions = ["nf.user_id = %s", "sl.user_id = %s"]
    params: list = [user_id, user_id]

    date_conditions = []
    if since is not None:
        date_conditions.append("nf.date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("nf.date <= %s")
        params.append(until)

    all_conditions = conditions + date_conditions
    where = "WHERE " + " AND ".join(all_conditions)

    sql = f"""
        SELECT
            nf.food_name,
            nf.category,
            nf.meal_group,
            nf.date,
            sl.date                                                          AS sleep_date,
            ROUND((sl.total_in_bed_time_milli     / 3600000.0)::numeric, 2) AS total_in_bed_hours,
            sl.sleep_performance_percentage                                  AS sleep_performance_pct,
            sl.sleep_efficiency_percentage                                   AS sleep_efficiency_pct,
            ROUND((sl.total_slow_wave_sleep_milli / 3600000.0)::numeric, 2) AS slow_wave_sleep_hours,
            ROUND((sl.total_rem_sleep_milli       / 3600000.0)::numeric, 2) AS rem_sleep_hours,
            nf.energy_kcal,
            nf.protein_g,
            nf.carbs_g,
            nf.fat_g,
            nf.fiber_g
        FROM nutrition_foods nf
        JOIN sleep sl
          ON sl.date = nf.date + INTERVAL '1 day'
         AND sl.is_nap = FALSE
         AND sl.score_state = 'SCORED'
        {where}
          AND (
              nf.meal_group IN ('Dinner', 'Snack')
              OR nf.logged_at >= '17:00:00'
          )
        ORDER BY nf.date, nf.food_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_food_vs_recovery(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """For each food item eaten on day N, pairs it with the recovery score on day N+1.

    Mirrors get_nutrition_vs_recovery from correlations.py but at food-item granularity
    rather than daily aggregate, so the agent can identify specific foods that correlate
    with high or low recovery.

    Returns a list of dicts with keys:
        food_name, category, meal_group, date, recovery_date,
        recovery_score, hrv_rmssd_milli, resting_heart_rate,
        energy_kcal, protein_g, carbs_g, fat_g, fiber_g
    """
    conditions = ["nf.user_id = %s", "r.user_id = %s", "r.score_state = 'SCORED'"]
    params: list = [user_id, user_id]

    date_conditions = []
    if since is not None:
        date_conditions.append("nf.date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("nf.date <= %s")
        params.append(until)

    all_conditions = conditions + date_conditions
    where = "WHERE " + " AND ".join(all_conditions)

    sql = f"""
        SELECT
            nf.food_name,
            nf.category,
            nf.meal_group,
            nf.date,
            r.date              AS recovery_date,
            r.recovery_score,
            r.hrv_rmssd_milli,
            r.resting_heart_rate,
            nf.energy_kcal,
            nf.protein_g,
            nf.carbs_g,
            nf.fat_g,
            nf.fiber_g
        FROM nutrition_foods nf
        JOIN recovery r ON r.date = nf.date + INTERVAL '1 day'
        {where}
        ORDER BY nf.date, nf.food_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_food_vs_body_composition(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
    days_window: int = 7,
) -> list[dict]:
    """For each food item eaten on a given day, aggregates daily macro totals and pairs
    them with the nearest body measurement within days_window days.

    Mirrors get_nutrition_vs_body_composition from correlations.py but at food-item
    granularity, returning one row per (food_name, date) pair so the agent can identify
    specific foods that appear alongside changes in body composition metrics.

    Returns a list of dicts with keys:
        food_name, category, date, measurement_date,
        weight_kg, fat_ratio, muscle_mass_kg,
        daily_energy_kcal, daily_protein_g, daily_carbs_g, daily_fat_g
    """
    conditions = ["nf.user_id = %s"]
    # params order matches SQL placeholder order:
    #   1. CTE: nutrition_foods subquery WHERE user_id = %s
    #   2. CTE: body_measurements join bm.user_id = %s
    #   3. final WHERE: nf.user_id = %s
    #   4+. optional date conditions on nf.date
    params: list = [user_id, user_id, user_id]

    date_conditions = []
    if since is not None:
        date_conditions.append("nf.date >= %s")
        params.append(since)
    if until is not None:
        date_conditions.append("nf.date <= %s")
        params.append(until)

    all_conditions = conditions + date_conditions
    where = "WHERE " + " AND ".join(all_conditions)

    # days_window is a validated int — safe to interpolate directly
    sql = f"""
        WITH nearest_measurement AS (
            SELECT
                nf_dates.date AS food_date,
                bm.id         AS bm_id,
                ABS(bm.date - nf_dates.date) AS day_diff,
                ROW_NUMBER() OVER (
                    PARTITION BY nf_dates.date
                    ORDER BY ABS(bm.date - nf_dates.date)
                ) AS rn
            FROM (SELECT DISTINCT date FROM nutrition_foods WHERE user_id = %s) nf_dates
            JOIN body_measurements bm
              ON ABS(bm.date - nf_dates.date) <= {days_window}
             AND bm.user_id = %s
        )
        SELECT
            nf.food_name,
            nf.category,
            nf.date,
            bm.date                                              AS measurement_date,
            bm.weight_kg,
            bm.fat_ratio,
            bm.muscle_mass_kg,
            SUM(nf.energy_kcal) OVER (PARTITION BY nf.date)     AS daily_energy_kcal,
            SUM(nf.protein_g)   OVER (PARTITION BY nf.date)     AS daily_protein_g,
            SUM(nf.carbs_g)     OVER (PARTITION BY nf.date)     AS daily_carbs_g,
            SUM(nf.fat_g)       OVER (PARTITION BY nf.date)     AS daily_fat_g
        FROM nutrition_foods nf
        JOIN nearest_measurement nm ON nm.food_date = nf.date AND nm.rn = 1
        JOIN body_measurements bm   ON bm.id = nm.bm_id
        {where}
        ORDER BY nf.date, nf.food_name
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
