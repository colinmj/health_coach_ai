import json

from langchain_core.tools import tool

import analytics.food_correlations as fc
from db.schema import get_request_user_id


@tool
def get_food_vs_performance(since: str = "", until: str = "") -> str:
    """Use for questions like 'which foods do I eat before my best workouts?' or
    'what specific foods correlate with PR days?'.
    For each food item eaten on a workout day or the day before, counts how often
    it appeared on days with PR/Better sets vs non-PR days, along with average macros.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: food_name, category, meal_group,
    appearances_on_pr_days, appearances_on_non_pr_days,
    avg_protein_g, avg_carbs_g, avg_fat_g, avg_energy_kcal."""
    user_id = get_request_user_id()
    return json.dumps(
        fc.get_food_vs_performance(
            user_id=user_id,
            since=since.strip() or None,
            until=until.strip() or None,
        ),
        default=str,
    )


@tool
def get_food_vs_sleep(since: str = "", until: str = "") -> str:
    """Use for questions like 'does eating X before bed affect my sleep?' or
    'which evening foods correlate with better or worse sleep quality?'.
    Pairs dinner/snack foods (or items logged after 17:00) with the following
    night's sleep metrics: total time in bed, sleep performance score,
    slow-wave sleep, and REM sleep. Sleep durations are in hours.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: food_name, category, meal_group, date, sleep_date,
    total_in_bed_hours, sleep_performance_pct, sleep_efficiency_pct,
    slow_wave_sleep_hours, rem_sleep_hours,
    energy_kcal, protein_g, carbs_g, fat_g, fiber_g."""
    user_id = get_request_user_id()
    return json.dumps(
        fc.get_food_vs_sleep(
            user_id=user_id,
            since=since.strip() or None,
            until=until.strip() or None,
        ),
        default=str,
    )


@tool
def get_food_vs_recovery(since: str = "", until: str = "") -> str:
    """Use for questions like 'which foods help or hurt my recovery?' or
    'does eating X affect my HRV the next day?'.
    For each food item eaten on day N, pairs it with the Whoop recovery score
    and HRV on day N+1. Operates at food-item granularity so the agent can
    identify specific foods rather than just macro totals.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: food_name, category, meal_group, date,
    recovery_date, recovery_score, hrv_rmssd_milli, resting_heart_rate,
    energy_kcal, protein_g, carbs_g, fat_g, fiber_g."""
    user_id = get_request_user_id()
    return json.dumps(
        fc.get_food_vs_recovery(
            user_id=user_id,
            since=since.strip() or None,
            until=until.strip() or None,
        ),
        default=str,
    )


@tool
def get_food_vs_body_composition(
    since: str = "",
    until: str = "",
    days_window: str = "7",
) -> str:
    """Use for questions like 'which foods do I eat when my weight is lower?' or
    'does eating X correlate with body fat changes?'.
    For each food item eaten on a given day, aggregates that day's total macros
    and pairs them with the nearest body measurement within days_window days.
    days_window controls how many days before/after to look for a body measurement.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: food_name, category, date, measurement_date,
    weight_kg, fat_ratio, muscle_mass_kg,
    daily_energy_kcal, daily_protein_g, daily_carbs_g, daily_fat_g."""
    user_id = get_request_user_id()
    return json.dumps(
        fc.get_food_vs_body_composition(
            user_id=user_id,
            since=since.strip() or None,
            until=until.strip() or None,
            days_window=int(days_window) if days_window.strip() else 7,
        ),
        default=str,
    )
