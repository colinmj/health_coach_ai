"""Analytics functions for manually-logged workouts.

All functions query the manual_workouts/manual_exercises/manual_sets tables
and return list[dict] for consumption by agent tools.
"""

from db.schema import get_connection


def get_exercise_list(user_id: int) -> list[dict]:
    """Return manual exercise templates the user has logged, sorted by session count.

    Each dict has: exercise_template_id, exercise_title, session_count.
    Returns an empty list if the user has no manual workouts yet.
    """
    sql = """
        SELECT
            e.exercise_template_id,
            e.title         AS exercise_title,
            COUNT(DISTINCT w.id) AS session_count
        FROM manual_exercises e
        JOIN manual_workouts w ON e.workout_id = w.id
        WHERE w.user_id = %s
          AND e.exercise_template_id IS NOT NULL
        GROUP BY e.exercise_template_id, e.title
        ORDER BY session_count DESC, e.title
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    return [dict(row) for row in rows]


def get_exercise_prs(user_id: int, exercise_template_id: str | None = None) -> list[dict]:
    """All-time best estimated 1RM per exercise for manual workouts.

    Each dict has: exercise_template_id, exercise_title, pr_1rm_kg.
    Optionally filtered to a single exercise via exercise_template_id.
    Returns an empty list if no data is found.
    """
    params: list = [user_id]
    extra = ""
    if exercise_template_id is not None:
        extra = " AND e.exercise_template_id = %s"
        params.append(exercise_template_id)

    sql = f"""
        SELECT
            e.exercise_template_id,
            e.title                 AS exercise_title,
            MAX(s.estimated_1rm)    AS pr_1rm_kg
        FROM manual_sets s
        JOIN manual_exercises e ON s.exercise_id  = e.id
        JOIN manual_workouts  w ON e.workout_id   = w.id
        WHERE w.user_id = %s{extra}
        GROUP BY e.exercise_template_id, e.title
        ORDER BY pr_1rm_kg DESC NULLS LAST
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_recent_workouts_summary(user_id: int, weeks: int = 12) -> list[dict]:
    """Recent workout summary for agent context, covering the last N weeks.

    Each dict has: exercise_template_id, exercise_title, session_count,
    max_1rm_kg, avg_reps.
    Excludes warmup and dropset set types. Returns an empty list if no data.
    """
    sql = f"""
        SELECT
            e.exercise_template_id,
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
        GROUP BY e.exercise_template_id, e.title
        ORDER BY session_count DESC
        LIMIT 30
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    return [dict(row) for row in rows]
