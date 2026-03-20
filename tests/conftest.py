"""Shared fixtures for analytics tests.

Connects to the PostgreSQL database specified by DATABASE_URL (.env).
Each test gets a freshly seeded database — all data tables are truncated
before seeding so tests are fully isolated from each other.

Requires a running Postgres instance (e.g. `docker compose up -d db`).
"""

import os
from contextlib import contextmanager
from unittest.mock import patch

import psycopg
from psycopg.rows import dict_row
import pytest
from dotenv import load_dotenv

import db.schema as schema
from db.schema import init_db

load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def setup_schema():
    """Create all tables, views, and indexes once per test session."""
    init_db()


@pytest.fixture
def db():
    """Truncate all data tables, seed fresh data, and patch get_connection
    so analytics functions share the same connection for the duration of
    the test. The transaction is rolled back after each test.
    """
    conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=schema._serializable_row)

    # Truncate all data tables (CASCADE handles FK order)
    conn.execute(
        "TRUNCATE hevy_sets, hevy_exercises, hevy_workouts, "
        "sleep, recovery, body_measurements, nutrition_daily, "
        "sessions, messages, insights, user_integrations, users CASCADE"
    )
    conn.commit()

    _seed(conn)
    conn.commit()

    # Savepoint so test-specific writes don't bleed across tests
    conn.execute("SAVEPOINT test_start")

    @contextmanager
    def _get_conn():
        yield conn

    with patch("db.schema.get_connection", side_effect=_get_conn):
        yield conn

    conn.execute("ROLLBACK TO SAVEPOINT test_start")
    conn.close()


def _seed(conn: psycopg.Connection) -> None:
    # ------------------------------------------------------------------
    # Users — let SERIAL assign id to avoid advancing the sequence manually
    # ------------------------------------------------------------------
    user_id = conn.execute(
        "INSERT INTO users (email, name) VALUES ('test@localhost', 'Test User') RETURNING id"
    ).fetchone()["id"]

    # ------------------------------------------------------------------
    # Hevy — two workouts, two exercises, varied performance tags
    # ------------------------------------------------------------------
    w1 = conn.execute(
        "INSERT INTO hevy_workouts (user_id, hevy_id, title, start_time, end_time) "
        "VALUES (%s, 'w1', 'Push Day', '2024-01-10T10:00:00', '2024-01-10T11:00:00') RETURNING id",
        (user_id,),
    ).fetchone()["id"]
    w2 = conn.execute(
        "INSERT INTO hevy_workouts (user_id, hevy_id, title, start_time, end_time) "
        "VALUES (%s, 'w2', 'Push Day', '2024-01-17T10:00:00', '2024-01-17T11:00:00') RETURNING id",
        (user_id,),
    ).fetchone()["id"]

    e1 = conn.execute("INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, exercise_index) VALUES (%s, 'bench-001', 'Bench Press', 0) RETURNING id", (w1,)).fetchone()["id"]
    e2 = conn.execute("INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, exercise_index) VALUES (%s, 'squat-001', 'Squat', 1) RETURNING id", (w1,)).fetchone()["id"]
    e3 = conn.execute("INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, exercise_index) VALUES (%s, 'bench-001', 'Bench Press', 0) RETURNING id", (w2,)).fetchone()["id"]
    e4 = conn.execute("INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, exercise_index) VALUES (%s, 'squat-001', 'Squat', 1) RETURNING id", (w2,)).fetchone()["id"]

    # Workout 1: first time doing both exercises → PR
    # Workout 2: bench improves (Better), squat drops (Worse)
    for ex_id, weight, e1rm, tag in [
        (e1, 80.0,  93.33,  "PR"),
        (e2, 100.0, 116.67, "PR"),
        (e3, 85.0,  99.17,  "Better"),
        (e4, 95.0,  110.83, "Worse"),
    ]:
        conn.execute(
            "INSERT INTO hevy_sets (exercise_id, set_index, set_type, weight_kg, reps, estimated_1rm, performance_tag) "
            "VALUES (%s, 0, 'normal', %s, 5, %s, %s)",
            (ex_id, weight, e1rm, tag),
        )

    # ------------------------------------------------------------------
    # Whoop — recovery and sleep for the nights before each workout
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT INTO recovery (user_id, whoop_cycle_id, date, source, score_state, recovery_score, hrv_rmssd_milli, resting_heart_rate) "
        "VALUES (%s, 'cyc-1', '2024-01-09', 'whoop', 'SCORED', 85.0, 65.0, 52.0), "
        "       (%s, 'cyc-2', '2024-01-16', 'whoop', 'SCORED', 42.0, 38.0, 61.0)",
        (user_id, user_id),
    )

    conn.execute(
        "INSERT INTO sleep (user_id, whoop_sleep_id, whoop_cycle_id, date, source, is_nap, score_state, "
        "start_time, end_time, total_in_bed_time_milli, total_slow_wave_sleep_milli, "
        "total_rem_sleep_milli, sleep_performance_percentage, sleep_efficiency_percentage) VALUES "
        "(%s, 'slp-1', 'cyc-1', '2024-01-09', 'whoop', FALSE, 'SCORED', "
        " '2024-01-09T22:00:00', '2024-01-10T06:00:00', 28800000, 5400000, 7200000, 88.0, 91.0), "
        "(%s, 'slp-2', 'cyc-2', '2024-01-16', 'whoop', FALSE, 'SCORED', "
        " '2024-01-16T23:30:00', '2024-01-17T05:30:00', 21600000, 3600000, 3600000, 61.0, 72.0)",
        (user_id, user_id),
    )

    # ------------------------------------------------------------------
    # Withings — body measurements near each workout
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT INTO body_measurements "
        "(user_id, withings_group_id, measured_at, date, source, weight_kg, fat_ratio, muscle_mass_kg, fat_free_mass_kg, bone_mass_kg) "
        "VALUES "
        "(%s, 1001, '2024-01-10T07:00:00+00:00', '2024-01-10', 'withings', 82.0, 0.18, 38.0, 67.0, 3.2), "
        "(%s, 1002, '2024-01-17T07:00:00+00:00', '2024-01-17', 'withings', 81.5, 0.175, 38.5, 67.2, 3.2)",
        (user_id, user_id),
    )
