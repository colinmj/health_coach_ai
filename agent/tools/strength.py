import json

from langchain_core.tools import tool

import analytics.hevy as hevy
import analytics.manual_workout as manual_workout_analytics
from db.schema import get_connection, get_request_user_id


def _workout_source() -> str:
    """Return the workout_source for the current request user, defaulting to 'hevy'."""
    user_id = get_request_user_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT workout_source FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return row["workout_source"] if row and row["workout_source"] else "hevy"


@tool
def get_exercise_prs(exercise_template_id: str = "") -> str:
    """Return all-time best estimated 1RM per exercise.
    Optionally pass an exercise_template_id to filter to one exercise.
    Routes to manual workout data if the user's workout_source is 'manual'.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title, pr_1rm_kg
    (manual) or also pr_weight_kg, pr_reps, workout_title, pr_date (hevy)."""
    eid = exercise_template_id.strip() or None
    if _workout_source() == "manual":
        user_id = get_request_user_id()
        return json.dumps(manual_workout_analytics.get_exercise_prs(user_id=user_id, exercise_template_id=eid))
    return json.dumps(hevy.get_exercise_prs(exercise_template_id=eid))


@tool
def get_workout_1rm_history(
    exercise_template_id: str = "",
    since: str = "",
    until: str = "",
) -> str:
    """Return best estimated 1RM per exercise per session over time.
    All args are optional. since/until are YYYY-MM-DD strings.
    Returns a JSON list of records with fields: workout_title, workout_date,
    exercise_template_id, exercise_title, session_best_1rm_kg, best_set_weight_kg, best_set_reps."""
    return json.dumps(hevy.get_workout_1rm_history(
        exercise_template_id=exercise_template_id.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_workout_performance(
    since: str = "",
    until: str = "",
    min_score: str = "",
) -> str:
    """Return workout-level performance summaries (PR/Better/Neutral/Worse set counts and score).
    All args are optional. since/until are YYYY-MM-DD strings. min_score is a float 0-3.
    Returns a JSON list of records with fields: workout_title, workout_date,
    total_sets, pr_sets, better_sets, neutral_sets, worse_sets, performance_score, best_tag."""
    return json.dumps(hevy.get_workout_performance(
        since=since.strip() or None,
        until=until.strip() or None,
        min_score=float(min_score) if min_score.strip() else None,
    ))


@tool
def get_exercise_list() -> str:
    """Return all known exercises with their template IDs and how many sessions they appear in.
    Use this to look up exercise_template_id values for other tools.
    Routes to manual workout data if the user's workout_source is 'manual'.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title, session_count."""
    if _workout_source() == "manual":
        user_id = get_request_user_id()
        return json.dumps(manual_workout_analytics.get_exercise_list(user_id=user_id))
    return json.dumps(hevy.get_exercise_template_ids())
