"""Shared sync utilities: last_synced_at tracking and throttle checks."""

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


def get_last_synced_at(user_id: int, domain: str) -> datetime | None:
    """Return the last successful sync time for a domain, or None if never synced."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT last_synced_at FROM user_integrations WHERE user_id = %s AND domain = %s",
            (user_id, domain),
        ).fetchone()
    return _parse_dt(row["last_synced_at"]) if row else None


def update_last_synced_at(user_id: int, domain: str, source: str) -> None:
    """Record a successful sync for a domain. Inserts the row if it doesn't exist yet."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO user_integrations (user_id, domain, source, last_synced_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id, domain) DO UPDATE SET
                last_synced_at = NOW(),
                source = EXCLUDED.source
            """,
            (user_id, domain, source),
        )


def needs_sync(user_id: int, domain: str) -> bool:
    """Return True if this domain has never been synced or was last synced
    more than SYNC_THROTTLE_MINUTES ago."""
    last = get_last_synced_at(user_id, domain)
    if last is None:
        return True
    return datetime.now(timezone.utc) - last > timedelta(minutes=SYNC_THROTTLE_MINUTES)
