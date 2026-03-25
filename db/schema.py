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


def get_request_user_id() -> int:
    """Return the user_id for the current request.

    Reads from the ContextVar set by set_current_user_id() (via API auth or astream_run).
    Raises RuntimeError if not set.
    """
    uid = _current_user_id.get()
    if uid is not None:
        return uid
    raise RuntimeError(
        "No user_id in context — set_current_user_id() must be called before invoking tools."
    )


def get_cli_user_id() -> int:
    """For CLI sync scripts: return the primary registered user's id.

    Looks up the first user in the DB (by id). Raises if no user exists yet.
    """
    with get_connection() as conn:
        row = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise RuntimeError("No users found. Register via the web app first.")
    return row["id"]
