"""Shared sync utilities: token management, last_synced_at tracking, throttle checks."""

from datetime import datetime, timedelta, timezone

from db.schema import get_connection

SYNC_THROTTLE_MINUTES = 5


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_integration_tokens(user_id: int, source: str) -> tuple[str, str]:
    """Fetch access_token and refresh_token from user_integrations."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT access_token, refresh_token FROM user_integrations WHERE user_id = %s AND source = %s",
            (user_id, source),
        ).fetchone()
    if not row or not row["access_token"]:
        raise RuntimeError(f"No credentials found for {source}. Connect via Settings.")
    return row["access_token"], row["refresh_token"] or ""


def save_integration_tokens(user_id: int, source: str, access_token: str, refresh_token: str) -> None:
    """Persist refreshed tokens back to user_integrations."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE user_integrations SET access_token = %s, refresh_token = %s WHERE user_id = %s AND source = %s",
            (access_token, refresh_token, user_id, source),
        )
        conn.commit()


def get_active_source(user_id: int, data_type: str) -> str | None:
    """Return which source the user has selected for a data type, or None if unset."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT source FROM user_data_imports WHERE user_id = %s AND data_type = %s",
            (user_id, data_type),
        ).fetchone()
    return row["source"] if row else None


def get_last_synced_at(user_id: int, source: str) -> datetime | None:
    """Return the last successful sync time for a source, or None if never synced."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_synced_at FROM user_integrations WHERE user_id = %s AND source = %s",
            (user_id, source),
        ).fetchone()
    return _parse_dt(row["last_synced_at"]) if row else None


def update_last_synced_at(user_id: int, source: str) -> None:
    """Record a successful sync for a source."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE user_integrations SET last_synced_at = NOW() WHERE user_id = %s AND source = %s",
            (user_id, source),
        )
        conn.commit()


def needs_sync(user_id: int, source: str) -> bool:
    """Return True if this source has never synced or was last synced more than SYNC_THROTTLE_MINUTES ago."""
    last = get_last_synced_at(user_id, source)
    if last is None:
        return True
    return datetime.now(timezone.utc) - last > timedelta(minutes=SYNC_THROTTLE_MINUTES)


def epley_1rm(weight_kg: float | None, reps: int | None) -> float | None:
    """Epley formula: weight × (1 + reps/30). Returns None if inputs missing."""
    if not weight_kg or not reps:
        return None
    if reps == 1:
        return round(weight_kg, 2)
    return round(weight_kg * (1 + reps / 30), 2)


def tag_performance(
    current_1rm: float | None,
    prev_best: float | None,
    all_time_best: float | None,
) -> str:
    """Assign PR/Better/Neutral/Worse tag."""
    if current_1rm is None:
        return "Neutral"
    if all_time_best is None:
        return "PR"
    if current_1rm > all_time_best:
        return "PR"
    if prev_best is None:
        return "Neutral"
    ratio = current_1rm / prev_best
    if ratio > 1.025:
        return "Better"
    if ratio < 0.975:
        return "Worse"
    return "Neutral"
