"""
Feature gate system.

Three enforcement points:
  1. require_feature()        — FastAPI route dependency (HTTP 403 before work starts)
  2. has_feature()            — inline conditional checks inside tools/analytics
  3. tool_requires_feature()  — LangChain tool decorator (returns error string instead of running)
"""

from __future__ import annotations

import logging
from functools import wraps

from fastapi import Depends, HTTPException

from api.auth import get_current_user_id
from api.tiers import FEATURE_MATRIX, FEATURE_MIN_TIER, Feature
from db.schema import get_connection, get_request_user_id

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def get_user_tier(user_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tier FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return row["tier"] if row else "free"


def has_feature(tier: str, feature: Feature) -> bool:
    """Return True if the given tier has access to the feature."""
    return feature in FEATURE_MATRIX.get(tier, set())


# ─── FastAPI route dependency ─────────────────────────────────────────────────

def require_feature(feature: Feature):
    """
    FastAPI dependency factory. Raises HTTP 403 if the current user's tier
    does not include the requested feature.

    Usage:
        @router.post("/analysis/regression")
        async def regression(_, = Depends(require_feature(Feature.LINEAR_REGRESSION))):
    """
    async def dependency(user_id: int = Depends(get_current_user_id)) -> None:
        tier = get_user_tier(user_id)
        if not has_feature(tier, feature):
            required = FEATURE_MIN_TIER.get(feature, "pro")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": f"This feature requires the {required.title()} plan.",
                    "required_tier": required,
                    "current_tier": tier,
                    "feature": feature.value,
                },
            )
    return Depends(dependency)


# ─── LangChain tool decorator ─────────────────────────────────────────────────

def tool_requires_feature(feature: Feature):
    """
    Decorator for LangChain tool functions. Reads the current user_id from the
    ContextVar set by the API auth dependency, looks up their tier, and returns
    an error string (visible to the agent) if the feature is not available.

    Apply ABOVE @tool so the check runs before LangChain wraps the function.

    Usage:
        @tool_requires_feature(Feature.LINEAR_REGRESSION)
        @tool
        def analyze_correlation(...):
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                user_id = get_request_user_id()
                tier = get_user_tier(user_id)
            except RuntimeError:
                logger.warning("tool_requires_feature: no user_id in context for %s", fn.__name__)
                return f"[Cannot verify feature access — no user context. Please re-authenticate.]"

            if not has_feature(tier, feature):
                required = FEATURE_MIN_TIER.get(feature, "pro")
                return (
                    f"[This analysis requires the {required.title()} plan. "
                    f"Your current plan ({tier}) does not include {feature.value}. "
                    f"Upgrade to unlock this feature.]"
                )
            return fn(*args, **kwargs)

        # Preserve the function name and docstring so LangChain's @tool sees them correctly
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator


def check_tool_feature(feature: Feature) -> str | None:
    """
    Inline check for use inside a LangChain tool body.

    Returns an error string (to return from the tool) if the current user's tier
    does not have access, or None if access is granted.

    Usage:
        @tool
        def analyze_correlation(...) -> str:
            if err := check_tool_feature(Feature.LINEAR_REGRESSION):
                return err
            ...
    """
    try:
        user_id = get_request_user_id()
        tier = get_user_tier(user_id)
    except RuntimeError:
        return "[Cannot verify feature access — no user context. Please re-authenticate.]"

    if not has_feature(tier, feature):
        required = FEATURE_MIN_TIER.get(feature, "pro")
        return (
            f"[This analysis requires the {required.title()} plan. "
            f"Your current plan ({tier}) does not include {feature.value}. "
            f"Upgrade to unlock this feature.]"
        )
    return None
