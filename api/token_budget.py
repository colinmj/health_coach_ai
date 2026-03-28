"""
Token budget middleware.

Two-layer protection:
  1. check_budget_dependency — FastAPI dependency, pre-flight monthly + per-query check
  2. TokenBudgetCallback — LangChain callback, accumulates tokens mid-run and raises
     if the per-query cap is hit; persists usage after the run (including partial runs).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, HTTPException
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from api.auth import get_current_user_id
from api.tiers import TIERS
from db.schema import get_connection

logger = logging.getLogger(__name__)


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _get_tokens_used(user_id: int, period: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tokens_used FROM token_usage WHERE user_id = %s AND period = %s",
            (user_id, period),
        ).fetchone()
    return row["tokens_used"] if row else 0


def _get_user_tier(user_id: int) -> str:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tier FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    return row["tier"] if row else "free"


def increment_usage(user_id: int, tokens: int) -> None:
    """Add tokens to the current month's usage (upsert)."""
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO token_usage (user_id, period, tokens_used, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, period)
            DO UPDATE SET
                tokens_used = token_usage.tokens_used + EXCLUDED.tokens_used,
                updated_at  = EXCLUDED.updated_at
            """,
            (user_id, period, tokens, now),
        )


# ─── Pre-flight FastAPI dependency ────────────────────────────────────────────

async def check_budget_dependency(
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """
    FastAPI dependency. Checks monthly balance before any agent work starts.

    Returns budget context dict so the route can pass it to astream_run:
      {"user_id", "tier", "remaining", "per_query_cap"}

    Raises HTTP 402 on:
      - monthly_budget_exhausted  — balance is zero
      - insufficient_budget       — remaining < 25% of per-query cap
    """
    period = datetime.now(timezone.utc).strftime("%Y-%m")
    tier = _get_user_tier(user_id)
    tier_cfg = TIERS.get(tier, TIERS["free"])
    monthly_limit = tier_cfg["monthly_tokens"]
    per_query_cap = tier_cfg["per_query_tokens"]

    tokens_used = _get_tokens_used(user_id, period)
    remaining = monthly_limit - tokens_used

    # First day of next month as reset hint for UI
    now = datetime.now(timezone.utc)
    if now.month == 12:
        resets = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc).isoformat()
    else:
        resets = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc).isoformat()

    if remaining <= 0:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "monthly_budget_exhausted",
                "message": "You've used your monthly token allocation. Your budget resets on the 1st.",
                "resets": resets,
                "tier": tier,
            },
        )

    if remaining < per_query_cap * 0.25:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "insufficient_budget",
                "message": f"You have {remaining:,} tokens remaining — not enough for a full query. Your budget resets on the 1st.",
                "remaining": remaining,
                "resets": resets,
                "tier": tier,
            },
        )

    return {
        "user_id": user_id,
        "tier": tier,
        "remaining": remaining,
        "per_query_cap": per_query_cap,
    }


# ─── LangChain mid-run callback ───────────────────────────────────────────────

class TokenBudgetExceeded(Exception):
    """Raised mid-run when the per-query token cap is hit."""
    pass


class TokenBudgetCallback(BaseCallbackHandler):
    """
    Accumulates token usage across all LLM steps in a ReAct loop.
    Raises TokenBudgetExceeded if the per-query cap is hit.
    Persists total usage to DB after the run (call flush() in a finally block).
    """

    def __init__(self, user_id: int, per_query_cap: int) -> None:
        super().__init__()
        self.user_id = user_id
        self.per_query_cap = per_query_cap
        self._total_tokens = 0
        self._flushed = False

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        for generations in response.generations:
            for gen in generations:
                usage = getattr(gen, "generation_info", None) or {}
                # Anthropic usage comes through generation_info
                input_tokens = usage.get("input_tokens", 0) or 0
                output_tokens = usage.get("output_tokens", 0) or 0
                # Also check response.llm_output for some providers
                if input_tokens == 0 and output_tokens == 0:
                    llm_out = response.llm_output or {}
                    usage_meta = llm_out.get("usage", {}) or {}
                    input_tokens = usage_meta.get("input_tokens", 0) or 0
                    output_tokens = usage_meta.get("output_tokens", 0) or 0
                self._total_tokens += input_tokens + output_tokens

        if self._total_tokens >= self.per_query_cap:
            logger.warning(
                "Per-query cap hit: user=%s used=%d cap=%d",
                self.user_id, self._total_tokens, self.per_query_cap,
            )
            raise TokenBudgetExceeded(
                f"Per-query token limit of {self.per_query_cap:,} reached."
            )

    def flush(self) -> None:
        """Persist accumulated tokens to DB. Call in a finally block."""
        if self._flushed or self._total_tokens == 0:
            return
        self._flushed = True
        try:
            increment_usage(self.user_id, self._total_tokens)
        except Exception:
            logger.exception("Failed to persist token usage for user %s", self.user_id)

    @property
    def total_tokens(self) -> int:
        return self._total_tokens
