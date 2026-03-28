import json

from langchain_core.tools import tool

import analytics.nutrition as nutrition
from db.schema import get_request_user_id


@tool
def get_food_entries(since: str = "", until: str = "", meal_group: str = "") -> str:
    """Return individual food items logged in Cronometer.
    since/until: optional YYYY-MM-DD strings.
    meal_group: optional filter — 'Breakfast', 'Lunch', 'Dinner', 'Snack', etc.
    Returns a JSON list with fields: date, logged_at, meal_group, food_name, amount,
    category, energy_kcal, protein_g, carbs_g, net_carbs_g, fat_g, fiber_g."""
    user_id = get_request_user_id()
    return json.dumps(nutrition.get_food_entries(
        user_id=user_id,
        since=since.strip() or None,
        until=until.strip() or None,
        meal_group=meal_group.strip() or None,
    ))


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
