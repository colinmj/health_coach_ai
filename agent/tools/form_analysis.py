import json

from langchain_core.tools import tool

from db.schema import get_connection, get_request_user_id


@tool
def get_form_analyses(exercise_name: str = "", limit: int = 10) -> str:
    """Use for questions about lifting form, technique assessments, or form check results.
    Returns past video form analyses including findings, coaching cues, overall rating,
    and the recovery score on the day of each analysis (useful for correlating form
    quality with fatigue or recovery).
    exercise_name is optional — omit to return all exercises, or pass e.g. "barbell_squat"
    to filter. Supported values: barbell_squat, deadlift, bench_press, overhead_press.
    Returns a JSON list with fields: exercise_name, video_date, overall_rating, findings,
    cues, recovery_score_day_of."""
    user_id = get_request_user_id()

    conditions = ["user_id = %s"]
    params: list = [user_id]

    if exercise_name.strip():
        conditions.append("exercise_name = %s")
        params.append(exercise_name.strip().lower())

    params.append(max(1, min(limit, 50)))

    where = " AND ".join(conditions)
    sql = f"""
        SELECT exercise_name, video_date, overall_rating, findings, cues, recovery_score_day_of
        FROM form_analyses
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT %s
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["video_date"] = str(d["video_date"])
        d["recovery_score_day_of"] = (
            float(d["recovery_score_day_of"]) if d["recovery_score_day_of"] is not None else None
        )
        result.append(d)

    return json.dumps(result, default=str)
