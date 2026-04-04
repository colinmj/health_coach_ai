"""Shared constants and helpers for the tools package."""

from db.schema import get_connection

_DOMAIN_ALLOWLIST = {"strength", "recovery", "body_composition", "nutrition"}
_CONFIDENCE_RANK = {"strong": 2, "moderate": 1}

DEFAULT_SOURCES: dict[str, str] = {
    "strength":         "hevy",
    "recovery":         "whoop",
    "body_composition": "withings",
    "nutrition":        "cronometer",
}


def build_source_map(user_id: int) -> dict[str, str]:
    """Return domain→source map for only the integrations this user has active.

    Strength source is determined by users.workout_source (not user_integrations),
    defaulting to 'manual' if unset. All other domains require an active row in
    user_integrations.
    """
    with get_connection() as conn:
        integration_rows = conn.execute(
            "SELECT source FROM user_integrations WHERE user_id = %s AND is_active = TRUE",
            (user_id,),
        ).fetchall()
        user_row = conn.execute(
            "SELECT workout_source FROM users WHERE id = %s", (user_id,)
        ).fetchone()

    connected = {row["source"] for row in integration_rows}
    source_map: dict[str, str] = {}

    # Strength — determined by workout_source on the user profile, never assumed
    workout_source = (user_row.get("workout_source") if user_row else None) or "manual"
    if workout_source in ("hevy", "manual", "strong"):
        source_map["strength"] = workout_source

    # Recovery
    if "whoop" in connected:
        source_map["recovery"] = "whoop"
    elif "oura" in connected:
        source_map["recovery"] = "oura"

    # Body composition
    if "withings" in connected:
        source_map["body_composition"] = "withings"
    elif "apple_health" in connected:
        source_map["body_composition"] = "apple_health"

    # Nutrition
    if "cronometer" in connected:
        source_map["nutrition"] = "cronometer"

    # Bloodwork
    if "bloodwork" in connected:
        source_map["bloodwork"] = "bloodwork"

    return source_map
