import datetime
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

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
    # Split on semicolons — safe because our schema has no semicolons inside strings.
    # Don't filter on startswith("--"): a statement may be preceded by a comment block
    # and Postgres handles leading comments fine.
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with get_connection() as conn:
        for stmt in statements:
            conn.execute(stmt)


def get_local_user_id() -> int:
    """Get or create the single local user, returning their id.

    Called by sync scripts to obtain a user_id for all inserts.
    In multi-user mode this will be replaced by proper auth context.
    """
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
        user_id = row["id"]

        # Seed integration rows so the UI can show status before any sync runs.
        # ON CONFLICT does nothing — preserves last_synced_at once populated.
        conn.execute(
            """
            INSERT INTO user_integrations (user_id, domain, source, load_type) VALUES
                (%s, 'strength',         'hevy',        'sync'),
                (%s, 'recovery',         'whoop',       'sync'),
                (%s, 'body_composition', 'withings',    'sync'),
                (%s, 'nutrition',        'cronometer',  'upload')
            ON CONFLICT (user_id, domain) DO UPDATE SET
                source    = EXCLUDED.source,
                load_type = EXCLUDED.load_type
            """,
            (user_id, user_id, user_id, user_id),
        )

        return user_id
