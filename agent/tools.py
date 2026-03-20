import json
from langchain_core.tools import tool

import analytics.hevy as hevy
import analytics.whoop as whoop
import analytics.withings as withings
import analytics.nutrition as nutrition
import analytics.correlations as corr


# ---------------------------------------------------------------------------
# Strength tools  (domain: "strength")
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Recovery tools  (domain: "recovery")
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Body composition tools  (domain: "body_composition")
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Nutrition tools  (domain: "nutrition")
# ---------------------------------------------------------------------------

@tool
def get_nutrition(since: str = "", until: str = "") -> str:
    """Return daily macros and key performance micros from Cronometer.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, source, energy_kcal, protein_g,
    carbs_g, net_carbs_g, fat_g, fiber_g, sugars_g, magnesium_mg, sodium_mg,
    potassium_mg, vitamin_d_iu, iron_mg, calcium_mg, completed."""
    return json.dumps(nutrition.get_nutrition(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


# ---------------------------------------------------------------------------
# Correlation tools  (domain pairs — all domains they touch)
# ---------------------------------------------------------------------------

@tool
def get_hrv_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does HRV predict workout quality?' questions.
    Returns paired prior-night recovery data with each workout's performance score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, total_sets, prior_night_recovery_score, prior_night_hrv_milli, prior_night_rhr."""
    return json.dumps(corr.get_hrv_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does sleep quality affect training?' questions. Sleep durations are in minutes.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, prior_night_sleep_performance, prior_night_sleep_efficiency,
    prior_night_sws_minutes, prior_night_rem_minutes, prior_night_in_bed_minutes."""
    return json.dumps(corr.get_sleep_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep_threshold_vs_performance(
    threshold_hours: str = "7",
    since: str = "",
    until: str = "",
) -> str:
    """Use for 'does sleeping more/less than X hours affect workout performance?' questions.
    Compares average performance score and PR rate for workouts preceded by nights above vs
    below the threshold. Returns two summary rows (above_threshold / below_threshold) with
    workout_count, avg_performance_score, avg_sleep_minutes, pr_workouts, better_workouts,
    worse_workouts. Default threshold is 7 hours."""
    return json.dumps(corr.get_sleep_threshold_vs_performance(
        threshold_hours=float(threshold_hours) if threshold_hours.strip() else 7.0,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_body_composition_vs_strength(
    since: str = "",
    until: str = "",
    days_window: str = "7",
) -> str:
    """Use for 'does body fat change track with strength?' questions.
    days_window controls how many days after a measurement to look for a workout.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: measurement_date, weight_kg, fat_ratio,
    muscle_mass_kg, fat_free_mass_kg, nearest_workout_date,
    avg_1rm_kg_across_exercises, exercises_tracked."""
    return json.dumps(corr.get_body_composition_vs_strength(
        since=since.strip() or None,
        until=until.strip() or None,
        days_window=int(days_window) if days_window.strip() else 7,
    ))


@tool
def get_nutrition_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does nutrition affect workout quality?' questions (carbs, calories, etc.).
    Pairs same-day nutrition with each workout's performance score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, energy_kcal, protein_g, carbs_g, net_carbs_g, fat_g, fiber_g."""
    return json.dumps(corr.get_nutrition_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_protein_vs_strength(since: str = "", until: str = "") -> str:
    """Use for 'does protein intake correlate with strength over time?' questions.
    Pairs daily protein with average session 1RM on workout days.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, protein_g, energy_kcal,
    avg_session_1rm_kg, exercise_count."""
    return json.dumps(corr.get_protein_vs_strength(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_nutrition_vs_recovery(since: str = "", until: str = "") -> str:
    """Use for 'does what I eat affect my recovery?' questions.
    Pairs prior-day nutrition with next-day Whoop recovery score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: recovery_date, recovery_score, hrv_rmssd_milli,
    prior_day_energy_kcal, prior_day_protein_g, prior_day_carbs_g, prior_day_fat_g."""
    return json.dumps(corr.get_nutrition_vs_recovery(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_carbs_prior_to_prs(since: str = "", until: str = "") -> str:
    """Use for 'did carb loading before PRs?' or 'carb intake before best workouts?' questions.
    For each PR workout, returns carb totals for each of the 3 prior days plus a 3-day average.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, pr_sets,
    carbs_day_minus_1, net_carbs_day_minus_1, carbs_day_minus_2, net_carbs_day_minus_2,
    carbs_day_minus_3, net_carbs_day_minus_3, avg_carbs_3d, avg_net_carbs_3d."""
    return json.dumps(corr.get_carbs_prior_to_prs(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_nutrition_vs_body_composition(
    since: str = "",
    until: str = "",
    days_window: str = "7",
) -> str:
    """Use for 'does calorie/macro intake correlate with body composition?' questions.
    days_window controls how many days around a nutrition entry to look for a body measurement.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, energy_kcal, protein_g, carbs_g, fat_g,
    weight_kg, fat_ratio, muscle_mass_kg."""
    return json.dumps(corr.get_nutrition_vs_body_composition(
        since=since.strip() or None,
        until=until.strip() or None,
        days_window=int(days_window) if days_window.strip() else 7,
    ))


# ---------------------------------------------------------------------------
# Registry — maps each tool to the domains and sources it requires.
#
# required_domains: the tool is excluded if any of these domains are not active.
# required_sources: the tool is excluded if the active source for a domain
#                   doesn't match. Omit a domain here to accept any source.
#
# Example: get_workout_performance requires strength=hevy because it relies on
# Hevy's performance tagging (PR/Better/Neutral/Worse). A Strong user with
# no equivalent tagging would not receive this tool.
# ---------------------------------------------------------------------------

TOOL_REGISTRY: list[tuple] = [
    # (tool_fn,                          required_domains,              required_sources)
    (get_exercise_prs,                   {"strength"},                  {"strength": "hevy"}),
    (get_workout_1rm_history,            {"strength"},                  {"strength": "hevy"}),
    (get_workout_performance,            {"strength"},                  {"strength": "hevy"}),
    (get_exercise_list,                  {"strength"},                  {"strength": "hevy"}),
    (get_recovery,                       {"recovery"},                  {}),
    (get_sleep,                          {"recovery"},                  {}),
    (get_body_composition,               {"body_composition"},          {}),
    (get_nutrition,                      {"nutrition"},                 {}),
    (get_hrv_vs_performance,             {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_vs_performance,           {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_threshold_vs_performance, {"recovery", "strength"},      {"strength": "hevy"}),
    (get_body_composition_vs_strength,   {"body_composition", "strength"}, {"strength": "hevy"}),
    (get_nutrition_vs_performance,       {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_protein_vs_strength,            {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_carbs_prior_to_prs,             {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_nutrition_vs_recovery,          {"nutrition", "recovery"},     {}),
    (get_nutrition_vs_body_composition,  {"nutrition", "body_composition"}, {}),
]

# Default source map for single-user local mode
DEFAULT_SOURCES: dict[str, str] = {
    "strength":         "hevy",
    "recovery":         "whoop",
    "body_composition": "withings",
    "nutrition":        "cronometer",
}


def build_tools(source_map: dict[str, str] = DEFAULT_SOURCES) -> list:
    """Return tools whose required domains and sources are satisfied by source_map.

    source_map maps domain → active source, e.g.:
        {"strength": "hevy", "recovery": "oura"}
    Tools requiring a domain not in source_map are excluded.
    Tools requiring a specific source for a domain are excluded if it doesn't match.
    """
    active_domains = set(source_map.keys())
    return [
        tool_fn
        for tool_fn, required_domains, required_sources in TOOL_REGISTRY
        if required_domains.issubset(active_domains)
        and all(source_map.get(domain) == source for domain, source in required_sources.items())
    ]


# Default: all tools (single-user local mode)
TOOLS = build_tools()
