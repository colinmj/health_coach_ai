from db.schema import get_connection


def get_exercise_prs(user_id: int, exercise_template_id: str | None = None) -> list[dict]:
    """All-time best estimated 1RM per exercise for a user, optionally filtered to one exercise."""
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if exercise_template_id is not None:
        conditions.append("exercise_template_id = %s")
        params.append(exercise_template_id)
    sql = "SELECT * FROM v_exercise_prs WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_workout_1rm_history(
    user_id: int,
    exercise_template_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Best 1RM per exercise per session for a user, with optional exercise and date filters."""
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if exercise_template_id is not None:
        conditions.append("exercise_template_id = %s")
        params.append(exercise_template_id)
    if since is not None:
        conditions.append("workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("workout_date <= %s")
        params.append(until)
    sql = "SELECT * FROM v_workout_1rm WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_workout_performance(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
    min_score: float | None = None,
) -> list[dict]:
    """Workout-level performance summary for a user, optionally filtered by date range or minimum score."""
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if since is not None:
        conditions.append("workout_date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("workout_date <= %s")
        params.append(until)
    if min_score is not None:
        conditions.append("performance_score >= %s")
        params.append(min_score)
    sql = "SELECT * FROM v_workout_performance WHERE " + " AND ".join(conditions)
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_recent_workouts(
    user_id: int,
    n_workouts: int = 3,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Set-level detail for the N most recent Hevy workouts."""
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
        FROM hevy_workouts  w
        JOIN hevy_exercises e ON e.workout_id  = w.id
        JOIN hevy_sets      s ON s.exercise_id = e.id
        WHERE w.id IN (
            SELECT id FROM hevy_workouts
            WHERE {where}
            ORDER BY start_time DESC
            LIMIT %s
        )
        ORDER BY w.start_time DESC, e.exercise_index, s.set_index
    """  # noqa: S608
    with get_connection() as conn:
        rows = conn.execute(sql, params + [n_workouts]).fetchall()
    return [dict(row) for row in rows]


def get_exercise_template_ids(user_id: int) -> list[dict]:
    """All known exercises for a user with their template IDs and session counts."""
    sql = """
        SELECT
            e.exercise_template_id,
            e.title AS exercise_title,
            COUNT(DISTINCT w.id) AS session_count
        FROM hevy_exercises e
        JOIN hevy_workouts w ON e.workout_id = w.id
        WHERE e.exercise_template_id IS NOT NULL
          AND w.user_id = %s
        GROUP BY e.exercise_template_id, e.title
        ORDER BY session_count DESC, e.title
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (user_id,)).fetchall()
    return [dict(row) for row in rows]
