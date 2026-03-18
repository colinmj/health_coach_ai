import json
from langchain_core.tools import tool

import analytics.hevy as hevy
import analytics.whoop as whoop
import analytics.withings as withings


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


@tool
def get_recovery(since: str = "", until: str = "") -> str:
    """Return Whoop recovery scores and HRV data.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, recovery_score, hrv_rmssd_milli,
    resting_heart_rate, spo2_percentage, skin_temp_celsius."""
    return json.dumps(whoop.get_recovery(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep(since: str = "", until: str = "", exclude_naps: bool = True) -> str:
    """Return Whoop sleep performance and architecture data.
    since/until are optional YYYY-MM-DD strings. exclude_naps defaults to True.
    Returns a JSON list of records with fields: date, sleep_performance_percentage,
    sleep_efficiency_percentage, total_rem_sleep_milli, total_slow_wave_sleep_milli,
    total_in_bed_time_milli, respiratory_rate."""
    return json.dumps(whoop.get_sleep(
        since=since.strip() or None,
        until=until.strip() or None,
        exclude_naps=exclude_naps,
    ))


@tool
def get_body_composition(since: str = "", until: str = "") -> str:
    """Return Withings body composition measurements (weight, fat %, muscle mass, etc.).
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, weight_kg, fat_ratio,
    muscle_mass_kg, fat_free_mass_kg, bone_mass_kg."""
    return json.dumps(withings.get_body_composition(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


TOOLS = [
    get_exercise_prs,
    get_workout_1rm_history,
    get_workout_performance,
    get_exercise_list,
    get_recovery,
    get_sleep,
    get_body_composition,
]
