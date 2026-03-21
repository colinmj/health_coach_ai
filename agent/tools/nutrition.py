import json

from langchain_core.tools import tool

import analytics.nutrition as nutrition


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
