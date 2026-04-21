"""
Tier configuration — single source of truth for all limits, features, and Stripe mappings.
"""

from enum import Enum


# ─── Tier token budgets ────────────────────────────────────────────────────────

TIERS: dict[str, dict] = {
    "free":    {"monthly_tokens": 75_000,    "per_query_tokens": 6_000},
    "starter": {"monthly_tokens": 600_000,   "per_query_tokens": 10_000},
    "pro":     {"monthly_tokens": 2_000_000, "per_query_tokens": 20_000},
    "elite":   {"monthly_tokens": 5_000_000, "per_query_tokens": 40_000},
}

TIER_ORDER = ["free", "starter", "pro", "elite"]


def tier_index(tier: str) -> int:
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0


# ─── Features ─────────────────────────────────────────────────────────────────

class Feature(str, Enum):
    BASIC_INSIGHTS      = "basic_insights"
    WORKOUT_LOGGING     = "workout_logging"
    NUTRITION_UPLOAD    = "nutrition_upload"
    RECOVERY_SYNC       = "recovery_sync"
    BODY_COMPOSITION    = "body_composition"
    ADVANCED_INSIGHTS   = "advanced_insights"
    GOAL_TRACKING       = "goal_tracking"
    INSIGHT_HISTORY     = "insight_history"
    LINEAR_REGRESSION   = "linear_regression"
    PROTOCOLS           = "protocols"
    AI_COACHING         = "ai_coaching"
    RAG_SPORTS_SCIENCE  = "rag_sports_science"
    PROGRESS_PHOTOS     = "progress_photos"
    MULTIPLE_REGRESSION = "multiple_regression"
    BLOODWORK_ANALYSIS  = "bloodwork_analysis"
    GENETIC_DATA        = "genetic_data"
    VIDEO_FORM_ANALYSIS = "video_form_analysis"


_FREE_FEATURES: set[Feature] = {
    Feature.BASIC_INSIGHTS,
    Feature.WORKOUT_LOGGING,
    Feature.NUTRITION_UPLOAD,
    Feature.RECOVERY_SYNC,
    Feature.BODY_COMPOSITION,
}

_STARTER_FEATURES: set[Feature] = _FREE_FEATURES | {
    Feature.ADVANCED_INSIGHTS,
    Feature.GOAL_TRACKING,
    Feature.INSIGHT_HISTORY,
}

_PRO_FEATURES: set[Feature] = _STARTER_FEATURES | {
    Feature.LINEAR_REGRESSION,
    Feature.PROTOCOLS,
    Feature.AI_COACHING,
    Feature.RAG_SPORTS_SCIENCE,
    Feature.PROGRESS_PHOTOS,
}

_ELITE_FEATURES: set[Feature] = _PRO_FEATURES | {
    Feature.MULTIPLE_REGRESSION,
    Feature.BLOODWORK_ANALYSIS,
    Feature.GENETIC_DATA,
    Feature.VIDEO_FORM_ANALYSIS,
}

FEATURE_MATRIX: dict[str, set[Feature]] = {
    "free":    _FREE_FEATURES,
    "starter": _STARTER_FEATURES,
    "pro":     _PRO_FEATURES,
    "elite":   _ELITE_FEATURES,
}

# Minimum tier required for each feature (for upgrade messaging)
FEATURE_MIN_TIER: dict[Feature, str] = {
    feature: next(
        tier for tier in TIER_ORDER
        if feature in FEATURE_MATRIX.get(tier, set())
    )
    for feature in Feature
}


# ─── Per-tool invocation limits (daily, monthly) ──────────────────────────────
# Format: {"tier": (daily_limit, monthly_limit)}
# Omitting a tier means that tool is not available on that tier.

TOOL_LIMITS: dict[str, dict[str, tuple[int, int]]] = {
    "coaching_query": {
        "free":    (3,  20),
        "starter": (5,  60),
        "pro":     (15, 200),
        "elite":   (30, 500),
    },
    "rag_sports_science": {
        "pro":   (10, 150),
        "elite": (20, 400),
    },
    "linear_regression": {
        "pro":   (20, 300),
        "elite": (50, 800),
    },
    "multiple_regression": {
        "elite": (5, 40),
    },
    "bloodwork_analysis": {
        "elite": (3, 20),
    },
}


def get_tool_limits(tool_name: str, tier: str) -> tuple[int, int] | None:
    """Return (daily_limit, monthly_limit) for a tool+tier, or None if unlimited/unavailable."""
    limits = TOOL_LIMITS.get(tool_name)
    if limits is None:
        return None  # No limit defined for this tool
    return limits.get(tier)  # None if tier not in limits (tool blocked at feature gate level)


# ─── Cooldown windows (minutes) ───────────────────────────────────────────────

COOLDOWNS: dict[str, int] = {
    "bloodwork_analysis":  24 * 60,
    "multiple_regression": 60,
    "linear_regression":   30,
    "rag_sports_science":  5,
    "coaching_query":      2,
}


# ─── Stripe price → tier mapping ──────────────────────────────────────────────
# Populate with real Stripe price IDs once products are created in Stripe dashboard.
# e.g. "price_1ABC123": "starter"

STRIPE_PRICE_TO_TIER: dict[str, str] = {
    # "price_XXXXXXXXXXXXXXXX": "starter",
    # "price_XXXXXXXXXXXXXXXX": "pro",
    # "price_XXXXXXXXXXXXXXXX": "elite",
}
