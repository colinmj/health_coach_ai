"""Classify activity/sport names into broad categories.

Used at sync time to populate the activity_category column on the activities table.
"""

_CARDIO_KEYWORDS = {
    "run", "cycling", "ride", "swim", "row", "hike", "walk", "ski",
    "snowboard", "elliptical", "stair", "cardio", "treadmill", "trail",
    "triathlon", "bike", "mtb", "xc", "jog", "sprint", "marathon",
    "cross country", "nordic", "skate",
}

_STRENGTH_KEYWORDS = {
    "weight", "lift", "strength", "crossfit", "powerlifting", "olympic",
    "barbell", "dumbbell", "kettlebell", "functional", "resistance",
}

_FLEXIBILITY_KEYWORDS = {
    "yoga", "pilates", "stretch", "mobility", "meditat", "breathwork",
    "flexibility", "foam roll",
}

_SPORT_KEYWORDS = {
    "basketball", "soccer", "football", "tennis", "hockey", "baseball",
    "volleyball", "lacrosse", "martial", "boxing", "kickbox", "wrestling",
    "rugby", "cricket", "golf", "paddle", "racket", "squash", "handball",
    "pickleball", "badminton", "water polo", "polo", "fencing",
}


def classify_activity(sport_name: str | None, source: str = "") -> str:
    """Return 'cardio' | 'strength' | 'flexibility' | 'sport' | 'other'.

    Matches are case-insensitive substring checks. 'other' is the fallback.
    """
    if not sport_name:
        return "other"
    name = sport_name.lower()
    if any(k in name for k in _CARDIO_KEYWORDS):
        return "cardio"
    if any(k in name for k in _STRENGTH_KEYWORDS):
        return "strength"
    if any(k in name for k in _FLEXIBILITY_KEYWORDS):
        return "flexibility"
    if any(k in name for k in _SPORT_KEYWORDS):
        return "sport"
    return "other"
