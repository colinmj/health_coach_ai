"""Shared fixtures for analytics tests.

Connects to the PostgreSQL database specified by DATABASE_URL (.env).
Each test runs inside a single transaction that is fully rolled back at the
end — including the TRUNCATE and seed. The real database is never modified.

Requires a running Postgres instance (e.g. `docker compose up -d db`).
"""

import os
from contextlib import contextmanager, ExitStack
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

    # Fail fast if another connection is holding locks (e.g. a previous test run
    # that was killed before it could roll back). Without this, TRUNCATE hangs.
    conn.execute("SET lock_timeout = '5s'")

    # Truncate and seed within the transaction — never committed, fully rolled
    # back at the end so the real database is left completely untouched.
    conn.execute(
        "TRUNCATE hevy_sets, hevy_exercises, hevy_workouts, "
        "sleep, recovery, whoop_activities, body_measurements, nutrition_daily, "
        "action_compliance, actions, protocols, goals, "
        "sessions, messages, insights, user_integrations, users CASCADE"
    )

    _seed(conn)

    # Savepoint so writes made during the test don't bleed into the next test
    conn.execute("SAVEPOINT test_start")

    @contextmanager
    def _get_conn():
        yield conn

    # Patch every module that imported get_connection directly at import time.
    # Patching only db.schema won't affect those modules — they hold their own
    # reference to the original function and would create real connections that
    # block on the TRUNCATE's AccessExclusiveLock.
    _modules = [
        "db.schema",
        "analytics.hevy",
        "analytics.whoop",
        "analytics.withings",
        "analytics.nutrition",
        "analytics.correlations",
        "analytics.goals",
        "analytics.compliance",
        "analytics.trends",
        "agent.tools",
        "agent.sessions",
        "db.queries.metrics",
    ]
    with ExitStack() as stack:
        for mod in _modules:
            try:
                stack.enter_context(patch(f"{mod}.get_connection", side_effect=_get_conn))
            except AttributeError:
                pass  # module not imported yet or doesn't use get_connection
        yield conn

    conn.execute("ROLLBACK TO SAVEPOINT test_start")
    conn.rollback()  # rolls back truncation + seed — real DB untouched
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

    # ------------------------------------------------------------------
    # Nutrition — daily entries for the two workout weeks
    # ------------------------------------------------------------------
    conn.execute(
        "INSERT INTO nutrition_daily (user_id, date, source, energy_kcal, protein_g, carbs_g, fat_g) VALUES "
        "(%s, '2024-01-09', 'cronometer', 2200.0, 160.0, 240.0, 70.0), "
        "(%s, '2024-01-10', 'cronometer', 2500.0, 180.0, 280.0, 75.0), "
        "(%s, '2024-01-16', 'cronometer', 1900.0, 130.0, 200.0, 65.0), "
        "(%s, '2024-01-17', 'cronometer', 2100.0, 150.0, 220.0, 68.0)",
        (user_id, user_id, user_id, user_id),
    )

    # ------------------------------------------------------------------
    # Goals, protocols, actions, insights
    # ------------------------------------------------------------------
    goal_id = conn.execute(
        "INSERT INTO goals (user_id, raw_input, goal_text, domains, target_date) "
        "VALUES (%s, 'I want to build strength', 'Increase upper body strength', "
        "'[\"strength\"]'::jsonb, '2024-06-01') RETURNING id",
        (user_id,),
    ).fetchone()["id"]

    protocol_id = conn.execute(
        "INSERT INTO protocols (user_id, goal_id, insight_ids, protocol_text, start_date, review_date) "
        "VALUES (%s, %s, '[]'::jsonb, 'Train bench press 3x per week and eat high protein', "
        "'2024-01-01', '2024-02-01') RETURNING id",
        (user_id, goal_id),
    ).fetchone()["id"]

    action1_id = conn.execute(
        "INSERT INTO actions (protocol_id, user_id, action_text, metric, condition, target_value, data_source, frequency) "
        "VALUES (%s, %s, 'Lift at least 3x per week', 'workout_frequency', 'greater_than', 2, 'hevy', 'weekly') RETURNING id",
        (protocol_id, user_id),
    ).fetchone()["id"]

    action2_id = conn.execute(
        "INSERT INTO actions (protocol_id, user_id, action_text, metric, condition, target_value, data_source, frequency) "
        "VALUES (%s, %s, 'Eat at least 160g protein per day', 'protein_g', 'greater_than', 160, 'cronometer', 'daily') RETURNING id",
        (protocol_id, user_id),
    ).fetchone()["id"]

    conn.execute(
        "INSERT INTO insights (user_id, correlative_tool, insight, effect, confidence, date_derived, pinned) VALUES "
        "(%s, 'get_sleep_vs_performance', 'Better sleep leads to more PR sets', 'positive', 'strong', '2024-01-17', TRUE), "
        "(%s, 'get_recovery', 'Low HRV means worse performance', 'negative', 'moderate', '2024-01-10', FALSE)",
        (user_id, user_id),
    )

    # store these for tests that need them
    conn._test_ids = {
        "user_id": user_id,
        "goal_id": goal_id,
        "protocol_id": protocol_id,
        "action1_id": action1_id,
        "action2_id": action2_id,
    }
