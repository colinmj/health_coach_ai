"""
Per-tool invocation rate limits.

Checks daily and monthly invocation caps from the tool_usage table.
Raises HTTP 429 when a cap is hit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from api.tiers import TOOL_LIMITS
from db.schema import get_connection

logger = logging.getLogger(__name__)


def _get_tool_row(user_id: int, tool_name: str, date: str) -> dict | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT invocations, tokens_used, last_input_hash, last_result, last_invoked_at "
            "FROM tool_usage WHERE user_id = %s AND tool_name = %s AND date = %s",
            (user_id, tool_name, date),
        ).fetchone()


def _get_monthly_invocations(user_id: int, tool_name: str, month: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(invocations), 0) AS total "
            "FROM tool_usage WHERE user_id = %s AND tool_name = %s AND month = %s",
            (user_id, tool_name, month),
        ).fetchone()
    return int(row["total"]) if row else 0


def check_tool_limits(user_id: int, tool_name: str, tier: str) -> None:
    """
    Raise HTTP 429 if the user has hit the daily or monthly invocation cap
    for the given tool on their current tier.

    No-op for tools that have no entry in TOOL_LIMITS.
    """
    tier_limits = TOOL_LIMITS.get(tool_name)
    if tier_limits is None:
        return  # No limit defined for this tool

    limits = tier_limits.get(tier)
    if limits is None:
        return  # Tool accessible (gated by feature, not here) or no limit on this tier

    daily_limit, monthly_limit = limits
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    daily_row = _get_tool_row(user_id, tool_name, date_str)
    daily_used = daily_row["invocations"] if daily_row else 0

    if daily_used >= daily_limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "daily_limit_reached",
                "message": f"You've reached the daily limit ({daily_limit}) for {tool_name}. Resets tomorrow.",
                "tool": tool_name,
                "daily_used": daily_used,
                "daily_limit": daily_limit,
            },
        )

    monthly_used = _get_monthly_invocations(user_id, tool_name, month_str)
    if monthly_used >= monthly_limit:
        raise HTTPException(
            status_code=429,
            detail={
                "error": "monthly_limit_reached",
                "message": f"You've reached the monthly limit ({monthly_limit}) for {tool_name}. Resets next month.",
                "tool": tool_name,
                "monthly_used": monthly_used,
                "monthly_limit": monthly_limit,
            },
        )


def record_tool_invocation(
    user_id: int,
    tool_name: str,
    input_hash: str | None = None,
    result_json: str | None = None,
    tokens: int = 0,
) -> None:
    """Upsert a tool invocation into tool_usage (increment count, update hash + cached result)."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    month_str = now.strftime("%Y-%m")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tool_usage
                (user_id, tool_name, date, month, invocations, tokens_used,
                 last_input_hash, last_result, last_invoked_at)
            VALUES (%s, %s, %s, %s, 1, %s, %s, %s, %s)
            ON CONFLICT (user_id, tool_name, date)
            DO UPDATE SET
                invocations     = tool_usage.invocations + 1,
                tokens_used     = tool_usage.tokens_used + EXCLUDED.tokens_used,
                last_input_hash = COALESCE(EXCLUDED.last_input_hash, tool_usage.last_input_hash),
                last_result     = COALESCE(EXCLUDED.last_result,     tool_usage.last_result),
                last_invoked_at = EXCLUDED.last_invoked_at
            """,
            (
                user_id, tool_name, date_str, month_str, tokens,
                input_hash, result_json, now.isoformat(),
            ),
        )
