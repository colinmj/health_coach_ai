"""Shared constants for the tools package."""

_DOMAIN_ALLOWLIST = {"strength", "recovery", "body_composition", "nutrition"}
_CONFIDENCE_RANK = {"strong": 2, "moderate": 1}

DEFAULT_SOURCES: dict[str, str] = {
    "strength":         "hevy",
    "recovery":         "whoop",
    "body_composition": "withings",
    "nutrition":        "cronometer",
}
