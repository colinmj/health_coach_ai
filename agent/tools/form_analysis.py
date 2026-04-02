import json

from langchain_core.tools import tool

import analytics.form_analysis as form_analytics
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


@tool
def get_form_progression(exercise_name: str) -> str:
    """Use to track how lifting form quality for a specific exercise has changed over
    time, and how it lines up with strength at each point.

    Returns every form analysis session for the exercise in chronological order.
    Each row includes the overall_rating ('good', 'needs_work', 'safety_concern'),
    findings, coaching cues, and — if a Hevy strength session exists within 14 days
    of the video — the best 1RM from that session and the day offset (negative = before
    the video, positive = after).

    Use this when the user asks things like:
      - "How has my deadlift form progressed?"
      - "Is my squat technique getting better over time?"
      - "Show me my form history for bench press"

    exercise_name must be the slug used in form_analyses, e.g.: deadlift,
    barbell_squat, bench_press, overhead_press.

    Returns a JSON list. Returns an empty list if no form sessions exist for
    the exercise.
    """
    user_id = get_request_user_id()
    result = form_analytics.get_form_progression(user_id, exercise_name.strip().lower())
    if not result:
        return "No form analysis sessions found for that exercise."
    return json.dumps(result, default=str)


@tool
def get_form_vs_strength(exercise_name: str) -> str:
    """Use to compare strength outcomes (1RM) in the 30 days following form sessions
    grouped by form rating category.

    Answers: "Do my squat numbers improve more in the weeks after a good-form session
    than after a needs_work session?"

    Returns one row per overall_rating ('good', 'needs_work', 'safety_concern') with:
      - session_count: how many form sessions had that rating
      - avg_followup_1rm_kg: average best 1RM across all Hevy sessions in the 30 days after
      - avg_peak_followup_1rm_kg: the highest single 1RM seen in the 30-day follow-up window
      - avg_recovery_score: average recovery score on the days of form sessions
      - total_followup_sessions: count of Hevy sessions found in the follow-up window

    Use this when the user asks things like:
      - "Do my numbers improve after good form sessions?"
      - "Does form quality predict strength gains?"
      - "Compare my progress after good vs needs_work deadlift sessions"

    exercise_name must be the slug used in form_analyses, e.g.: deadlift,
    barbell_squat, bench_press, overhead_press.

    Returns a JSON list grouped by rating. Returns an empty list if no form sessions
    exist for the exercise.
    """
    user_id = get_request_user_id()
    result = form_analytics.get_form_vs_strength(user_id, exercise_name.strip().lower())
    if not result:
        return "No form analysis sessions found for that exercise."
    return json.dumps(result, default=str)
