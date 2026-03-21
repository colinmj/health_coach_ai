import json

from langchain_core.tools import tool

import analytics.correlations as corr
from db.schema import get_local_user_id


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
def get_nutrition_vs_activity(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Use for questions like 'how does carb/protein/fat intake the night before affect my
    performance in a specific sport?' (e.g. heart rate, strain, calories burned during hockey).
    Pairs prior-night nutrition with each activity session matching the sport.
    sport_name is matched case-insensitively. Leave blank to include all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: activity_date, sport_name, strain, avg_heart_rate,
    max_heart_rate, calories_burned, prior_night_energy_kcal, prior_night_carbs_g,
    prior_night_net_carbs_g, prior_night_protein_g, prior_night_fat_g, prior_night_sugars_g."""
    return json.dumps(corr.get_nutrition_vs_activity(
        sport_name=sport_name.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_activity_vs_strength(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Use for 'does a prior-day sport/activity affect lifting performance?' questions
    (e.g. 'do my workouts suffer the day after running/powerlifting/kickboxing?').
    Pairs each Hevy strength session with any Whoop activity logged the day before.
    sport_name is matched case-insensitively — leave blank to include all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, total_sets, prior_day_sport, prior_day_strain, prior_day_avg_hr,
    prior_day_max_hr, prior_day_calories."""
    return json.dumps(corr.get_activity_vs_strength(
        sport_name=sport_name.strip() or None,
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


@tool
def get_energy_balance_vs_weight(since: str = "", until: str = "") -> str:
    """Use for weight change goal questions: 'am I in a deficit?', 'why isn't my weight changing?',
    'is my calorie tracking accurate?', 'is Whoop overestimating my burn?'.
    Compares daily calories consumed (Cronometer) vs Whoop daily energy burn, then checks
    whether the resulting estimated surplus/deficit aligns with actual weight change.
    A large discrepancy between expected and actual weight change suggests a tracking error
    or inaccurate Whoop estimate.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, calories_consumed, calories_burned, daily_balance,
    rolling_7d_avg_consumed, rolling_7d_avg_burned, rolling_7d_avg_balance,
    rolling_7d_expected_weight_change_kg, weight_kg, weight_7d_ago_kg,
    actual_7d_weight_change_kg."""
    user_id = get_local_user_id()
    return json.dumps(corr.get_energy_balance_vs_weight(
        user_id=user_id,
        since=since.strip() or None,
        until=until.strip() or None,
    ))
