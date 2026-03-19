"""Shared fixtures for analytics tests.

Patches db.schema.DB_PATH to use an in-memory SQLite database, then seeds it
with a small but realistic dataset covering all three sources.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

import db.schema as schema
from db.schema import _CREATE_TABLES


@pytest.fixture
def db(tmp_path):
    """Yield a seeded in-memory connection and patch DB_PATH for the duration of the test."""
    db_file = tmp_path / "test.db"

    with patch.object(schema, "DB_PATH", db_file):
        schema.init_db()

        with schema.get_connection() as conn:
            _seed(conn)
            conn.commit()

        yield db_file


def _seed(conn: sqlite3.Connection) -> None:
    # ------------------------------------------------------------------
    # Hevy — two workouts, two exercises, varied performance tags
    # ------------------------------------------------------------------
    conn.execute("""
        INSERT INTO hevy_workouts (hevy_id, title, start_time, end_time)
        VALUES
            ('w1', 'Push Day', '2024-01-10T10:00:00', '2024-01-10T11:00:00'),
            ('w2', 'Push Day', '2024-01-17T10:00:00', '2024-01-17T11:00:00')
    """)

    conn.execute("""
        INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, exercise_index)
        VALUES
            (1, 'bench-001', 'Bench Press', 0),
            (1, 'squat-001', 'Squat',       1),
            (2, 'bench-001', 'Bench Press', 0),
            (2, 'squat-001', 'Squat',       1)
    """)

    # Workout 1: first time doing both exercises → PR
    # Workout 2: bench improves (Better), squat drops (Worse)
    conn.execute("""
        INSERT INTO hevy_sets
            (exercise_id, set_index, set_type, weight_kg, reps, estimated_1rm, performance_tag)
        VALUES
            (1, 0, 'normal', 80.0,  5, 93.33,  'PR'),
            (2, 0, 'normal', 100.0, 5, 116.67, 'PR'),
            (3, 0, 'normal', 85.0,  5, 99.17,  'Better'),
            (4, 0, 'normal', 95.0,  5, 110.83, 'Worse')
    """)

    # ------------------------------------------------------------------
    # Whoop — recovery and sleep for the nights before each workout
    # ------------------------------------------------------------------
    conn.execute("""
        INSERT INTO recovery
            (whoop_cycle_id, date, source, score_state, recovery_score,
             hrv_rmssd_milli, resting_heart_rate)
        VALUES
            ('cyc-1', '2024-01-09', 'whoop', 'SCORED', 85.0, 65.0, 52.0),
            ('cyc-2', '2024-01-16', 'whoop', 'SCORED', 42.0, 38.0, 61.0)
    """)

    conn.execute("""
        INSERT INTO sleep
            (whoop_sleep_id, whoop_cycle_id, date, source, is_nap, score_state,
             start_time, end_time,
             total_in_bed_time_milli, total_slow_wave_sleep_milli,
             total_rem_sleep_milli, sleep_performance_percentage,
             sleep_efficiency_percentage)
        VALUES
            ('slp-1', 'cyc-1', '2024-01-09', 'whoop', 0, 'SCORED',
             '2024-01-09T22:00:00', '2024-01-10T06:00:00',
             28800000, 5400000, 7200000, 88.0, 91.0),
            ('slp-2', 'cyc-2', '2024-01-16', 'whoop', 0, 'SCORED',
             '2024-01-16T23:30:00', '2024-01-17T05:30:00',
             21600000, 3600000, 3600000, 61.0, 72.0)
    """)

    # ------------------------------------------------------------------
    # Withings — body measurements near each workout
    # ------------------------------------------------------------------
    conn.execute("""
        INSERT INTO body_measurements
            (withings_group_id, measured_at, date, source,
             weight_kg, fat_ratio, muscle_mass_kg, fat_free_mass_kg, bone_mass_kg)
        VALUES
            (1001, '2024-01-10T07:00:00+00:00', '2024-01-10', 'withings',
             82.0, 0.18, 38.0, 67.0, 3.2),
            (1002, '2024-01-17T07:00:00+00:00', '2024-01-17', 'withings',
             81.5, 0.175, 38.5, 67.2, 3.2)
    """)
