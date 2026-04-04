import json

from langchain_core.tools import tool

import analytics.hevy as hevy
import analytics.manual_workout as manual_workout_analytics
from db.schema import get_connection, get_request_user_id

KG_TO_LBS = 2.205


def _user_prefs() -> dict:
    """Return workout_source and units for the current user."""
    user_id = get_request_user_id()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT workout_source, units FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if not row:
        return {"source": "hevy", "units": "metric"}
    return {
        "source": row["workout_source"] or "hevy",
        "units": row["units"] or "metric",
    }


def _maybe_convert_kg(rows: list[dict], units: str) -> list[dict]:
    """When units=imperial, rename *_kg fields to *_lbs and multiply by KG_TO_LBS."""
    if units != "imperial":
        return rows
    out = []
    for row in rows:
        new = {}
        for k, v in row.items():
            if k.endswith("_kg"):
                new[k[:-3] + "_lbs"] = round(v * KG_TO_LBS, 1) if v is not None else None
            else:
                new[k] = v
        out.append(new)
    return out


@tool
def get_exercise_prs(exercise_template_id: str = "") -> str:
    """Return all-time best estimated 1RM per exercise.
    Optionally pass an exercise_template_id to filter to one exercise.
    Routes to manual workout data if the user's workout_source is 'manual'.
    Weight fields are already in the user's preferred units:
    pr_1rm_kg (metric) or pr_1rm_lbs (imperial); pr_weight_kg/lbs, pr_reps, workout_title, pr_date (hevy)."""
    user_id = get_request_user_id()
    prefs = _user_prefs()
    eid = exercise_template_id.strip() or None
    if prefs["source"] == "manual":
        rows = manual_workout_analytics.get_exercise_prs(user_id=user_id, exercise_id=eid)
    else:
        rows = hevy.get_exercise_prs(user_id=user_id, exercise_template_id=eid)
    return json.dumps(_maybe_convert_kg(rows, prefs["units"]))


@tool
def get_workout_1rm_history(
    exercise_template_id: str = "",
    since: str = "",
    until: str = "",
) -> str:
    """Return best estimated 1RM per exercise per session over time.
    All args are optional. since/until are YYYY-MM-DD strings.
    Weight fields are already in the user's preferred units:
    session_best_1rm_kg/lbs, best_set_weight_kg/lbs, best_set_reps, workout_title, workout_date."""
    user_id = get_request_user_id()
    prefs = _user_prefs()
    eid = exercise_template_id.strip() or None
    since_ = since.strip() or None
    until_ = until.strip() or None
    if prefs["source"] == "manual":
        rows = manual_workout_analytics.get_1rm_history(
            user_id=user_id,
            exercise_id=eid,
            since=since_,
            until=until_,
        )
    else:
        rows = hevy.get_workout_1rm_history(
            user_id=user_id,
            exercise_template_id=eid,
            since=since_,
            until=until_,
        )
    return json.dumps(_maybe_convert_kg(rows, prefs["units"]))


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
    user_id = get_request_user_id()
    prefs = _user_prefs()
    since_ = since.strip() or None
    until_ = until.strip() or None
    if prefs["source"] == "manual":
        return json.dumps(manual_workout_analytics.get_workout_performance(
            user_id=user_id,
            since=since_,
            until=until_,
        ))
    return json.dumps(hevy.get_workout_performance(
        user_id=user_id,
        since=since_,
        until=until_,
        min_score=float(min_score) if min_score.strip() else None,
    ))


@tool
def get_recent_workouts(n_workouts: str = "3", since: str = "", until: str = "") -> str:
    """Return set-level detail for the N most recent workouts.
    n_workouts defaults to 3 (max 10). since/until are optional YYYY-MM-DD strings.
    Weight fields are already in the user's preferred units (weight_kg or weight_lbs).
    Returns a JSON list with fields: workout_title, workout_date, exercise_title,
    exercise_index, set_index, set_type, weight_kg/lbs, reps, rpe, performance_tag."""
    user_id = get_request_user_id()
    prefs = _user_prefs()
    n = min(int(n_workouts.strip() or "3"), 10)
    since_ = since.strip() or None
    until_ = until.strip() or None
    if prefs["source"] == "manual":
        rows = manual_workout_analytics.get_recent_workouts(
            user_id=user_id, n_workouts=n, since=since_, until=until_
        )
    else:
        rows = hevy.get_recent_workouts(
            user_id=user_id, n_workouts=n, since=since_, until=until_
        )
    return json.dumps(_maybe_convert_kg(rows, prefs["units"]))


@tool
def get_exercise_list() -> str:
    """Return all known exercises with their template IDs and how many sessions they appear in.
    Use this to look up exercise_template_id values for other tools.
    Routes to manual workout data if the user's workout_source is 'manual'.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title, session_count."""
    user_id = get_request_user_id()
    prefs = _user_prefs()
    if prefs["source"] == "manual":
        return json.dumps(manual_workout_analytics.get_exercise_list(user_id=user_id))
    return json.dumps(hevy.get_exercise_template_ids(user_id=user_id))
