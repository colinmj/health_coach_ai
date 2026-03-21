import json

from langchain_core.tools import tool

import analytics.withings as withings


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
