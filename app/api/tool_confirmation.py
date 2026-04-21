"""
Confirmation flow for expensive tool re-runs.

When an expensive tool (regression, bloodwork) is called with identical inputs
within its cooldown window, we surface the cached result and ask the user to confirm
before re-running.

Usage inside a LangChain tool:
    from api.tool_confirmation import check_confirmation, record_invocation, ConfirmationRequired

    @tool
    def analyze_correlation(rows_json: str) -> str:
        input_hash = fingerprint(rows_json)
        check_confirmation(tool_name="linear_regression", input_hash=input_hash)
        # ... run regression ...
        result = compute_regression(rows_json)
        record_invocation("linear_regression", input_hash, result)
        return result
"""

from __future__ import annotations

import hashlib
import json
import logging
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any

from api.tiers import COOLDOWNS
from api.tool_limits import record_tool_invocation
from db.schema import get_connection, get_request_user_id

logger = logging.getLogger(__name__)

# Propagated by the chat route for each request
_confirmed_cv: ContextVar[bool] = ContextVar("confirmed", default=False)

# Set by check_confirmation() when a tool needs user confirmation.
# Read by agent.py's streaming loop to emit the confirm_required event.
_pending_confirmation_cv: ContextVar["ConfirmationRequired | None"] = ContextVar(
    "pending_confirmation", default=None
)


def set_confirmed(confirmed: bool) -> None:
    """Called by the agent before a run to propagate the confirmed flag into tool context."""
    _confirmed_cv.set(confirmed)


def get_confirmed() -> bool:
    return _confirmed_cv.get()


def get_pending_confirmation() -> "ConfirmationRequired | None":
    """Read and clear the pending confirmation event. Called by the agent streaming loop."""
    exc = _pending_confirmation_cv.get()
    if exc is not None:
        _pending_confirmation_cv.set(None)
    return exc


# ─── Input fingerprinting ─────────────────────────────────────────────────────

def fingerprint(value: Any) -> str:
    """
    Normalise and SHA-256 hash a tool input.
    Returns the 16-char hex prefix (enough for dedup, not a security claim).
    """
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True)
    normalised = value.lower().strip()
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


# ─── Confirmation exception ───────────────────────────────────────────────────

class ConfirmationRequired(Exception):
    """
    Raised when a tool detects a duplicate recent run and the user hasn't confirmed.
    The agent catches this and emits a confirm_required SSE event.
    """
    def __init__(
        self,
        tool_name: str,
        last_run_ago: str,
        daily_used: int,
        daily_limit: int | None,
        cached_result: str | None,
    ) -> None:
        self.tool_name = tool_name
        self.last_run_ago = last_run_ago
        self.daily_used = daily_used
        self.daily_limit = daily_limit
        self.cached_result = cached_result
        super().__init__(f"confirm_required:{tool_name}")

    def to_event(self) -> dict:
        """Serialise to the SSE event payload the frontend expects."""
        return {
            "type": "confirm_required",
            "tool": self.tool_name,
            "title": f"You ran this analysis {self.last_run_ago}",
            "body": (
                "This is a compute-intensive analysis that consumes a significant portion "
                "of your token budget. The cached result is shown below. "
                "Run it again to refresh with the latest data?"
            ),
            "stats": {
                "last_run": self.last_run_ago,
                "daily_used": self.daily_used,
                "daily_limit": self.daily_limit,
            },
            "cached_result": self.cached_result,
        }


# ─── Core check ───────────────────────────────────────────────────────────────

def _get_last_invocation(user_id: int, tool_name: str, date: str) -> dict | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT invocations, last_input_hash, last_result, last_invoked_at "
            "FROM tool_usage WHERE user_id = %s AND tool_name = %s AND date = %s",
            (user_id, tool_name, date),
        ).fetchone()


def _get_daily_limit(user_id: int, tool_name: str) -> int | None:
    """Look up daily limit for user's tier. Returns None if no limit."""
    with get_connection() as conn:
        row = conn.execute("SELECT tier FROM users WHERE id = %s", (user_id,)).fetchone()
    tier = row["tier"] if row else "free"
    from api.tiers import TOOL_LIMITS
    tier_limits = TOOL_LIMITS.get(tool_name, {})
    limits = tier_limits.get(tier)
    return limits[0] if limits else None


def _format_ago(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - dt
    minutes = int(delta.total_seconds() / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    return f"{hours} hour{'s' if hours != 1 else ''} ago"


def check_confirmation(tool_name: str, input_hash: str) -> None:
    """
    Check whether this tool call should require user confirmation.

    Raises ConfirmationRequired when:
      - The same input hash was used within the tool's cooldown window
      - AND the user has not set confirmed=True on this request

    No-op when:
      - The tool has no cooldown defined
      - The input hash differs from the last run
      - confirmed=True is set on the current request
      - There is no prior invocation record
    """
    if get_confirmed():
        return  # User explicitly confirmed — skip soft checks

    cooldown_minutes = COOLDOWNS.get(tool_name)
    if cooldown_minutes is None:
        return  # No cooldown for this tool

    try:
        user_id = get_request_user_id()
    except RuntimeError:
        return  # No user context — let the tool run

    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    row = _get_last_invocation(user_id, tool_name, date_str)

    if row is None or row.get("last_invoked_at") is None:
        return  # No prior run today

    # Parse last_invoked_at
    last_str = row["last_invoked_at"]
    if isinstance(last_str, str):
        last_dt = datetime.fromisoformat(last_str.replace("Z", "+00:00"))
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    elif isinstance(last_str, datetime):
        last_dt = last_str if last_str.tzinfo else last_str.replace(tzinfo=timezone.utc)
    else:
        return

    # Check cooldown window
    if now - last_dt > timedelta(minutes=cooldown_minutes):
        return  # Outside cooldown — allow re-run without confirmation

    # Check input hash match
    if row.get("last_input_hash") != input_hash:
        return  # Different inputs — run immediately

    # Duplicate within cooldown — signal confirmation required via side-channel ContextVar.
    # The tool reads this after check_confirmation() returns and returns a deferred sentinel.
    # The agent streaming loop detects the pending event after the tool node completes.
    daily_limit = _get_daily_limit(user_id, tool_name)
    exc = ConfirmationRequired(
        tool_name=tool_name,
        last_run_ago=_format_ago(last_dt),
        daily_used=row.get("invocations", 1),
        daily_limit=daily_limit,
        cached_result=row.get("last_result"),
    )
    _pending_confirmation_cv.set(exc)
    raise exc


def record_invocation(
    tool_name: str,
    input_hash: str | None = None,
    result_json: str | None = None,
    tokens: int = 0,
) -> None:
    """Record a completed tool invocation (delegates to tool_limits.record_tool_invocation)."""
    try:
        user_id = get_request_user_id()
    except RuntimeError:
        return
    record_tool_invocation(user_id, tool_name, input_hash, result_json, tokens)
