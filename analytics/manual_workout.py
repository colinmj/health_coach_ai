"""Analytics functions for manually-logged workouts.

All functions query the manual_workouts/manual_exercises/manual_sets tables
and return list[dict] for consumption by agent tools.
"""

from db.schema import get_connection


def get_exercise_list(user_id: int) -> list[dict]:
    """Return exercises the user has logged manually, sorted by session count.

    Each dict has: exercise_id, exercise_title, session_count.
    Returns an empty list if the user has no manual workouts yet.
    """
    sql = """
        SELECT
            e.exercise_id,
            e.title         AS exercise_title,
            COUNT(DISTINCT w.id) AS session_count
        FROM manual_exercises e
        JOIN manual_workouts w ON e.workout_id = w.id
        WHERE w.user_id = %s
          AND e.exercise_id IS NOT NULL
        GROUP BY e.exercise_id, e.title
        ORDER BY session_count DESC, e.title
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    return [dict(row) for row in rows]


def get_exercise_prs(user_id: int, exercise_id: str | None = None) -> list[dict]:
    """All-time best estimated 1RM per exercise for manual workouts.

    Each dict has: exercise_id, exercise_title, pr_1rm_kg.
    Optionally filtered to a single exercise via exercise_id (UUID string).
    Returns an empty list if no data is found.
    """
    params: list = [user_id]
    extra = ""
    if exercise_id is not None:
        extra = " AND e.exercise_id = %s"
        params.append(exercise_id)

    sql = f"""
        SELECT
            e.exercise_id,
            e.title                 AS exercise_title,
            MAX(s.estimated_1rm)    AS pr_1rm_kg
        FROM manual_sets s
        JOIN manual_exercises e ON s.exercise_id  = e.id
        JOIN manual_workouts  w ON e.workout_id   = w.id
        WHERE w.user_id = %s{extra}
        GROUP BY e.exercise_id, e.title
        ORDER BY pr_1rm_kg DESC NULLS LAST
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_1rm_history(
    user_id: int,
    exercise_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Best 1RM per exercise per session for manual workouts.

    Each dict has: workout_title, workout_date, exercise_id,
    exercise_title, session_best_1rm_kg, best_set_weight_kg, best_set_reps.
    """
    conditions = ["w.user_id = %s"]
    params: list = [user_id]
    if exercise_id is not None:
        conditions.append("e.exercise_id = %s")
        params.append(exercise_id)
    if since is not None:
        conditions.append("w.start_time::date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("w.start_time::date <= %s")
        params.append(until)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            w.title                                          AS workout_title,
            w.start_time::date                               AS workout_date,
            e.exercise_id,
            e.title                                          AS exercise_title,
            ROUND(MAX(s.estimated_1rm)::numeric, 2)          AS session_best_1rm_kg,
            s.weight_kg                                      AS best_set_weight_kg,
            s.reps                                           AS best_set_reps
        FROM manual_workouts  w
        JOIN manual_exercises e ON e.workout_id  = w.id
        JOIN manual_sets      s ON s.exercise_id = e.id
        WHERE {where}
        GROUP BY w.title, workout_date, e.exercise_id, e.title,
                 s.weight_kg, s.reps
        ORDER BY workout_date, e.title
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_workout_performance(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Per-session PR/Better/Neutral/Worse breakdown for manual workouts.

    Each dict has: workout_title, workout_date, total_sets, pr_sets,
    better_sets, neutral_sets, worse_sets, performance_score, best_tag.
    """
    conditions = ["w.user_id = %s"]
    params: list = [user_id]
    if since is not None:
        conditions.append("w.start_time::date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("w.start_time::date <= %s")
        params.append(until)

    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            w.title                                          AS workout_title,
            w.start_time::date                               AS workout_date,
            COUNT(*)                                         AS total_sets,
            COUNT(*) FILTER (WHERE s.performance_tag = 'PR')       AS pr_sets,
            COUNT(*) FILTER (WHERE s.performance_tag = 'Better')   AS better_sets,
            COUNT(*) FILTER (WHERE s.performance_tag = 'Neutral')  AS neutral_sets,
            COUNT(*) FILTER (WHERE s.performance_tag = 'Worse')    AS worse_sets,
            COUNT(*) FILTER (WHERE s.performance_tag = 'Baseline') AS baseline_sets,
            -- Baseline sets contribute NULL so they are excluded from the average.
            -- A workout consisting entirely of first-time exercises yields NULL here.
            ROUND(AVG(CASE s.performance_tag
                WHEN 'PR'      THEN 3
                WHEN 'Better'  THEN 2
                WHEN 'Neutral' THEN 1
                WHEN 'Worse'   THEN 0
                ELSE NULL END)::numeric, 2)                  AS performance_score,
            CASE
                WHEN BOOL_AND(s.performance_tag = 'Baseline') THEN 'Baseline'
                WHEN MAX(CASE WHEN s.performance_tag = 'PR'     THEN 3 ELSE 0 END) = 3 THEN 'PR'
                WHEN MAX(CASE WHEN s.performance_tag = 'Better' THEN 2 ELSE 0 END) = 2 THEN 'Better'
                WHEN MAX(CASE WHEN s.performance_tag = 'Worse'  THEN 1 ELSE 0 END) = 1 THEN 'Neutral'
                ELSE 'Worse'
            END                                              AS best_tag
        FROM manual_workouts  w
        JOIN manual_exercises e ON e.workout_id  = w.id
        JOIN manual_sets      s ON s.exercise_id = e.id
        WHERE {where}
          AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
        GROUP BY w.id, w.title, workout_date
        ORDER BY workout_date DESC
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_recent_workouts(
    user_id: int,
    n_workouts: int = 3,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Set-level detail for the N most recent manually-logged workouts."""
    conditions = ["w.user_id = %s"]
    params: list = [user_id]
    if since:
        conditions.append("w.start_time::date >= %s")
        params.append(since)
    if until:
        conditions.append("w.start_time::date <= %s")
        params.append(until)
    where = " AND ".join(conditions)
    sql = f"""
        SELECT
            w.title            AS workout_title,
            w.start_time::date AS workout_date,
            e.title            AS exercise_title,
            e.exercise_index,
            s.set_index,
            s.set_type,
            s.weight_kg,
            s.reps,
            s.rpe,
            s.performance_tag
        FROM manual_workouts  w
        JOIN manual_exercises e ON e.workout_id  = w.id
        JOIN manual_sets      s ON s.exercise_id = e.id
        WHERE w.id IN (
            SELECT id FROM manual_workouts
            WHERE {where}
            ORDER BY start_time DESC
            LIMIT %s
        )
        ORDER BY w.start_time DESC, e.exercise_index, s.set_index
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params + [n_workouts]).fetchall()
    return [dict(row) for row in rows]


def get_recent_workouts_summary(user_id: int, weeks: int = 12) -> list[dict]:
    """Recent workout summary for agent context, covering the last N weeks.

    Each dict has: exercise_id, exercise_title, session_count,
    max_1rm_kg, avg_reps.
    Excludes warmup and dropset set types. Returns an empty list if no data.
    """
    sql = f"""
        SELECT
            e.exercise_id,
            e.title                              AS exercise_title,
            COUNT(DISTINCT w.id)                 AS session_count,
            ROUND(MAX(s.estimated_1rm)::numeric, 1)  AS max_1rm_kg,
            ROUND(AVG(s.reps)::numeric, 1)           AS avg_reps
        FROM manual_workouts  w
        JOIN manual_exercises e ON e.workout_id   = w.id
        JOIN manual_sets      s ON s.exercise_id  = e.id
        WHERE w.user_id = %s
          AND w.start_time >= NOW() - INTERVAL '{int(weeks)} weeks'
          AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
        GROUP BY e.exercise_id, e.title
        ORDER BY session_count DESC
        LIMIT 30
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    return [dict(row) for row in rows]
