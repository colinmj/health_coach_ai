import datetime
import os
from contextvars import ContextVar
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Set by the FastAPI JWT dependency for each request so all tools resolve
# the correct user without needing to thread user_id through every call.
_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def set_current_user_id(user_id: int) -> None:
    _current_user_id.set(user_id)

load_dotenv()

_SCHEMA_FILE = Path(__file__).parent / "postgres_schema.sql"


def _serializable_row(cursor):
    """Row factory that wraps dict_row and converts date/datetime/Decimal
    to JSON-safe types so analytics callers always get plain Python primitives."""
    base = dict_row(cursor)

    def make_row(values):
        row = base(values)
        if row is None:
            return {}
        return {
            k: (
                v.isoformat() if isinstance(v, datetime.date)
                else float(v) if isinstance(v, Decimal)
                else v
            )
            for k, v in row.items()
        }

    return make_row


def get_connection() -> psycopg.Connection[dict[str, Any]]:
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=_serializable_row)
    return conn


def init_db() -> None:
    """Create all tables, views, and indexes (idempotent)."""
    sql = _SCHEMA_FILE.read_text()
    with get_connection() as conn:
        conn.execute(sql)


def get_local_user_id() -> int:
    """Return the current user_id for this request/script.

    API requests: returns the id set by the JWT dependency via set_current_user_id().
    CLI sync scripts: falls back to the local single user (creates if needed).
    """
    uid = _current_user_id.get()
    if uid is not None:
        return uid

    # CLI fallback — create/fetch the local user (no integrations seeded here).
    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO users (email, name)
            VALUES ('local@localhost', 'Local User')
            ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
        ).fetchone()
        assert row is not None
        return row["id"]
