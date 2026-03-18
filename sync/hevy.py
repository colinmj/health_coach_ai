"""Sync Hevy workouts into SQLite.

Run:
    python -m sync.hevy

Each run is idempotent: existing workouts are updated, new ones are inserted.
Workouts are processed oldest-first so that previous-session comparisons are
accurate at insert time.
"""

import os
import sqlite3

from dotenv import load_dotenv

from clients.hevy import HevyClient
from db.schema import get_connection, init_db

load_dotenv()


# ---------------------------------------------------------------------------
# 1RM & performance tagging
# ---------------------------------------------------------------------------

def epley_1rm(weight_kg: float, reps: int) -> float | None:
    """Epley formula: weight × (1 + reps/30). Returns None for invalid input."""
    if not weight_kg or not reps:
        return None
    if reps == 1:
        return round(weight_kg, 2)
    return round(weight_kg * (1 + reps / 30), 2)


def _prev_session_best_1rm(
    conn: sqlite3.Connection,
    template_id: str,
    before_start_time: str,
) -> float | None:
    """Best estimated 1RM for an exercise in the most recent session before this one."""
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm)
        FROM sets s
        JOIN exercises e ON s.exercise_id = e.id
        JOIN workouts w  ON e.workout_id  = w.id
        WHERE e.exercise_template_id = ?
          AND w.start_time < ?
        """,
        (template_id, before_start_time),
    ).fetchone()
    return row[0] if row else None


def _all_time_best_1rm(
    conn: sqlite3.Connection,
    template_id: str,
    exclude_hevy_id: str,
) -> float | None:
    """All-time best estimated 1RM excluding the current workout."""
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm)
        FROM sets s
        JOIN exercises e ON s.exercise_id = e.id
        JOIN workouts w  ON e.workout_id  = w.id
        WHERE e.exercise_template_id = ?
          AND w.hevy_id != ?
        """,
        (template_id, exclude_hevy_id),
    ).fetchone()
    return row[0] if row else None


def tag_performance(
    current_1rm: float | None,
    prev_best: float | None,
    all_time_best: float | None,
) -> str:
    if current_1rm is None:
        return "Neutral"
    # No prior history → first time performing this exercise
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


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _upsert_workout(conn: sqlite3.Connection, workout: dict) -> int:
    hevy_id = workout["id"]
    row = conn.execute(
        "SELECT id FROM workouts WHERE hevy_id = ?", (hevy_id,)
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE workouts SET title=?, start_time=?, end_time=? WHERE id=?",
            (workout.get("title"), workout.get("start_time"), workout.get("end_time"), row[0]),
        )
        return row[0]

    cursor = conn.execute(
        "INSERT INTO workouts (hevy_id, title, start_time, end_time) VALUES (?,?,?,?)",
        (hevy_id, workout.get("title"), workout.get("start_time"), workout.get("end_time")),
    )
    return cursor.lastrowid


def _insert_exercises_and_sets(
    conn: sqlite3.Connection,
    workout_db_id: int,
    workout: dict,
) -> None:
    hevy_id = workout["id"]
    start_time = workout.get("start_time", "")

    # Wipe and re-insert so sets are always fresh (handles edited workouts)
    conn.execute("DELETE FROM exercises WHERE workout_id = ?", (workout_db_id,))

    for ex in workout.get("exercises", []):
        template_id = ex.get("exercise_template_id")

        cursor = conn.execute(
            """
            INSERT INTO exercises (workout_id, exercise_template_id, title, notes, exercise_index)
            VALUES (?,?,?,?,?)
            """,
            (workout_db_id, template_id, ex.get("title"), ex.get("notes"), ex.get("index")),
        )
        exercise_db_id = cursor.lastrowid

        # Baselines for tagging (only workouts already committed to DB)
        prev_best = _prev_session_best_1rm(conn, template_id, start_time)
        all_time_best = _all_time_best_1rm(conn, template_id, hevy_id)

        for s in ex.get("sets", []):
            e1rm = epley_1rm(s.get("weight_kg"), s.get("reps"))
            perf = tag_performance(e1rm, prev_best, all_time_best)

            conn.execute(
                """
                INSERT INTO sets
                    (exercise_id, set_index, set_type, weight_kg, reps,
                     duration_seconds, distance_meters, rpe, estimated_1rm, performance_tag)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    exercise_db_id,
                    s.get("index"),
                    s.get("set_type"),
                    s.get("weight_kg"),
                    s.get("reps"),
                    s.get("duration_seconds"),
                    s.get("distance_meters"),
                    s.get("rpe"),
                    e1rm,
                    perf,
                ),
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def sync_workouts() -> None:
    init_db()
    api_key = os.environ["HEVY_API_KEY"]

    print("Fetching workouts from Hevy…")
    with HevyClient(api_key) as client:
        # Collect all pages (API returns newest-first), then reverse so that
        # older workouts are inserted first and prev-session comparisons work.
        all_workouts = list(client.iter_workouts())

    all_workouts.sort(key=lambda w: w.get("start_time") or "")
    print(f"Processing {len(all_workouts)} workouts (oldest-first)…")

    with get_connection() as conn:
        for workout in all_workouts:
            db_id = _upsert_workout(conn, workout)
            _insert_exercises_and_sets(conn, db_id, workout)
            conn.commit()
            print(f"  ✓ {workout.get('title', 'Untitled')}  [{workout['id']}]")

    print("Sync complete.")


if __name__ == "__main__":
    sync_workouts()
