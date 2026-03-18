from db.schema import get_connection


def get_exercise_prs(exercise_template_id: str | None = None) -> list[dict]:
    """All-time best estimated 1RM per exercise, optionally filtered to one exercise."""
    sql = "SELECT * FROM v_exercise_prs"
    params: list = []
    if exercise_template_id is not None:
        sql += " WHERE exercise_template_id = ?"
        params.append(exercise_template_id)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_workout_1rm_history(
    exercise_template_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Best 1RM per exercise per session, with optional exercise and date filters."""
    conditions = []
    params: list = []
    if exercise_template_id is not None:
        conditions.append("exercise_template_id = ?")
        params.append(exercise_template_id)
    if since is not None:
        conditions.append("workout_date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("workout_date <= ?")
        params.append(until)
    sql = "SELECT * FROM v_workout_1rm"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_workout_performance(
    since: str | None = None,
    until: str | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Workout-level performance summary, optionally filtered by date range or minimum score."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("workout_date >= ?")
        params.append(since)
    if until is not None:
        conditions.append("workout_date <= ?")
        params.append(until)
    if min_score is not None:
        conditions.append("performance_score >= ?")
        params.append(min_score)
    sql = "SELECT * FROM v_workout_performance"
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_exercise_template_ids() -> list[dict]:
    """All known exercises with their template IDs and session counts."""
    sql = """
        SELECT
            e.exercise_template_id,
            e.title AS exercise_title,
            COUNT(DISTINCT w.id) AS session_count
        FROM exercises e
        JOIN workouts w ON e.workout_id = w.id
        WHERE e.exercise_template_id IS NOT NULL
        GROUP BY e.exercise_template_id, e.title
        ORDER BY session_count DESC, e.title
    """
    with get_connection() as conn:
        rows = conn.execute(sql).fetchall()
    return [dict(row) for row in rows]
