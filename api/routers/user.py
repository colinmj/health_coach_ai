"""
User tier, feature, and usage endpoints.

  GET /user/features   — accessible features + locked features with upgrade messaging
  GET /user/usage      — monthly token usage and quota
  GET /user/tool-usage — per-tool invocation counts, limits, and cooldown state
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from api.auth import get_current_user_id
from api.feature_gates import get_user_tier, has_feature
from api.tiers import (
    COOLDOWNS,
    FEATURE_MATRIX,
    FEATURE_MIN_TIER,
    TIER_ORDER,
    TIERS,
    TOOL_LIMITS,
    Feature,
    tier_index,
)
from db.schema import get_connection

router = APIRouter(prefix="/user", tags=["user"])


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_tokens_used(user_id: int, period: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM token_usage WHERE user_id = %s AND period = %s",
            (user_id, period),
        ).fetchone()
    return row["tokens_used"] if row else 0


def _get_all_tool_rows(user_id: int, date: str, month: str) -> dict[str, dict]:
    """Return {tool_name: row} for all tool_usage rows for today."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT tool_name, invocations, last_invoked_at FROM tool_usage "
            "WHERE user_id = %s AND date = %s",
            (user_id, date),
        ).fetchall()
    daily = {r["tool_name"]: r for r in rows}

    with get_connection() as conn:
        monthly_rows = conn.execute(
            "SELECT tool_name, SUM(invocations) AS total FROM tool_usage "
            "WHERE user_id = %s AND month = %s GROUP BY tool_name",
            (user_id, month),
        ).fetchall()
    monthly = {r["tool_name"]: int(r["total"]) for r in monthly_rows}

    return daily, monthly


def _is_in_cooldown(tool_name: str, last_invoked_at: str | datetime | None) -> bool:
    cooldown = COOLDOWNS.get(tool_name)
    if cooldown is None or last_invoked_at is None:
        return False
    if isinstance(last_invoked_at, str):
        last_dt = datetime.fromisoformat(last_invoked_at.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    else:
        last_dt = last_invoked_at if last_invoked_at.tzinfo else last_invoked_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_dt < timedelta(minutes=cooldown)


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/features")
async def get_user_features(user_id: int = Depends(get_current_user_id)) -> dict:
    """Return accessible features and locked features with upgrade messaging."""
    tier = get_user_tier(user_id)
    accessible = sorted(f.value for f in FEATURE_MATRIX.get(tier, set()))
    locked = []
    for feature in Feature:
        if not has_feature(tier, feature):
            required = FEATURE_MIN_TIER.get(feature, "pro")
            # Only show locked features from the next tier up
            if tier_index(required) > tier_index(tier):
                locked.append({
                    "feature": feature.value,
                    "required_tier": required,
                    "upgrade_message": f"Available on {required.title()} and above.",
                })
    return {
        "tier": tier,
        "features": accessible,
        "locked": locked,
    }


@router.get("/usage")
async def get_user_usage(user_id: int = Depends(get_current_user_id)) -> dict:
    """Return monthly token usage and quota for the current period."""
    tier = get_user_tier(user_id)
    tier_cfg = TIERS.get(tier, TIERS["free"])
    monthly_limit = tier_cfg["monthly_tokens"]

    now = datetime.now(timezone.utc)
    period = now.strftime("%Y-%m")
    tokens_used = _get_tokens_used(user_id, period)

    # First of next month
    if now.month == 12:
        resets_at = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        resets_at = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).isoformat()

    return {
        "tier": tier,
        "period": period,
        "tokens_used": tokens_used,
        "monthly_limit": monthly_limit,
        "remaining": max(0, monthly_limit - tokens_used),
        "percent_used": round(tokens_used / monthly_limit * 100, 1) if monthly_limit else 0,
        "resets_at": resets_at,
    }


@router.get("/tool-usage")
async def get_user_tool_usage(user_id: int = Depends(get_current_user_id)) -> dict:
    """Return per-tool invocation counts, limits, and cooldown state."""
    tier = get_user_tier(user_id)
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    daily_rows, monthly_totals = _get_all_tool_rows(user_id, date_str, month_str)

    tools = []
    for tool_name, tier_limits in TOOL_LIMITS.items():
        limits = tier_limits.get(tier)
        daily_limit = limits[0] if limits else None
        monthly_limit = limits[1] if limits else None

        daily_row = daily_rows.get(tool_name)
        daily_used = daily_row["invocations"] if daily_row else 0
        monthly_used = monthly_totals.get(tool_name, 0)
        last_invoked_at = daily_row["last_invoked_at"] if daily_row else None

        tools.append({
            "tool_name": tool_name,
            "daily_used": daily_used,
            "daily_limit": daily_limit,
            "monthly_used": monthly_used,
            "monthly_limit": monthly_limit,
            "last_invoked_at": last_invoked_at.isoformat() if isinstance(last_invoked_at, datetime) else last_invoked_at,
            "in_cooldown": _is_in_cooldown(tool_name, last_invoked_at),
            "cooldown_minutes": COOLDOWNS.get(tool_name),
        })

    return {"tier": tier, "tools": tools}
