import json

from langchain_core.tools import tool

import analytics.hevy as hevy


@tool
def get_exercise_prs(exercise_template_id: str = "") -> str:
    """Return all-time best estimated 1RM per exercise.
    Optionally pass an exercise_template_id to filter to one exercise.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title,
    pr_1rm_kg, pr_weight_kg, pr_reps, workout_title, pr_date."""
    eid = exercise_template_id.strip() or None
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
    Returns a JSON list of records with fields: exercise_template_id, exercise_title, session_count."""
    return json.dumps(hevy.get_exercise_template_ids())
