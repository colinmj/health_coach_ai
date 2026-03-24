"""Sync Hevy workouts into PostgreSQL.

Run:
    python -m sync.hevy

Each run is idempotent: existing workouts are updated, new ones are inserted.
Workouts are processed oldest-first so that previous-session comparisons are
accurate at insert time.
"""

import os
from typing import Any

import psycopg
from dotenv import load_dotenv

from clients.hevy import HevyClient
from db.schema import get_connection, get_local_user_id, init_db
from sync.utils import get_integration_tokens, get_last_synced_at, update_last_synced_at

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
    conn: psycopg.Connection[dict[str, Any]],
    template_id: str,
    before_start_time: str,
    user_id: int,
) -> float | None:
    """Best estimated 1RM for an exercise in the most recent session before this one."""
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm) AS best
        FROM hevy_sets s
        JOIN hevy_exercises e ON s.exercise_id = e.id
        JOIN hevy_workouts w  ON e.workout_id  = w.id
        WHERE e.exercise_template_id = %s
          AND w.start_time < %s
          AND w.user_id = %s
        """,
        (template_id, before_start_time, user_id),
    ).fetchone()
    return row["best"] if row and row["best"] is not None else None


def _all_time_best_1rm(
    conn: psycopg.Connection[dict[str, Any]],
    template_id: str,
    exclude_hevy_id: str,
    user_id: int,
) -> float | None:
    """All-time best estimated 1RM excluding the current workout."""
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm) AS best
        FROM hevy_sets s
        JOIN hevy_exercises e ON s.exercise_id = e.id
        JOIN hevy_workouts w  ON e.workout_id  = w.id
        WHERE e.exercise_template_id = %s
          AND w.hevy_id != %s
          AND w.user_id = %s
        """,
        (template_id, exclude_hevy_id, user_id),
    ).fetchone()
    return row["best"] if row and row["best"] is not None else None


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

def _upsert_workout(conn: psycopg.Connection[dict[str, Any]], workout: dict, user_id: int) -> int:
    hevy_id = workout["id"]
    row = conn.execute(
        "SELECT id FROM hevy_workouts WHERE hevy_id = %s AND user_id = %s",
        (hevy_id, user_id),
    ).fetchone()

    if row:
        conn.execute(
            "UPDATE hevy_workouts SET title=%s, start_time=%s, end_time=%s WHERE id=%s",
            (workout.get("title"), workout.get("start_time"), workout.get("end_time"), row["id"]),
        )
        return row["id"]

    inserted = conn.execute(
        """
        INSERT INTO hevy_workouts (user_id, hevy_id, title, start_time, end_time)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, hevy_id, workout.get("title"), workout.get("start_time"), workout.get("end_time")),
    ).fetchone()
    assert inserted is not None
    return inserted["id"]


def _insert_exercises_and_sets(
    conn: psycopg.Connection[dict[str, Any]],
    workout_db_id: int,
    workout: dict,
    user_id: int,
) -> None:
    hevy_id = workout["id"]
    start_time = workout.get("start_time", "")

    # Wipe and re-insert so sets are always fresh (handles edited workouts)
    conn.execute("DELETE FROM hevy_exercises WHERE workout_id = %s", (workout_db_id,))

    for ex in workout.get("exercises", []):
        template_id = ex.get("exercise_template_id")

        exercise_row = conn.execute(
            """
            INSERT INTO hevy_exercises (workout_id, exercise_template_id, title, notes, exercise_index)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (workout_db_id, template_id, ex.get("title"), ex.get("notes"), ex.get("index")),
        ).fetchone()
        assert exercise_row is not None
        exercise_db_id = exercise_row["id"]

        # Baselines for tagging (only workouts already committed to DB)
        prev_best = _prev_session_best_1rm(conn, template_id, start_time, user_id)
        all_time_best = _all_time_best_1rm(conn, template_id, hevy_id, user_id)

        for s in ex.get("sets", []):
            e1rm = epley_1rm(s.get("weight_kg"), s.get("reps"))
            perf = tag_performance(e1rm, prev_best, all_time_best)

            conn.execute(
                """
                INSERT INTO hevy_sets
                    (exercise_id, set_index, set_type, weight_kg, reps,
                     duration_seconds, distance_meters, rpe, estimated_1rm, performance_tag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
    user_id = get_local_user_id()
    api_key, _ = get_integration_tokens(user_id, "hevy")

    # Hevy has no API-level date filter, so we stop paginating early once we
    # hit workouts older than the last sync (API returns newest-first).
    last = get_last_synced_at(user_id, "strength")
    since = last.isoformat() if last else None
    if since:
        print(f"Incremental sync from {since}")

    print("Fetching workouts from Hevy…")
    all_workouts: list[dict] = []
    with HevyClient(api_key) as client:
        for workout in client.iter_workouts():
            start_time = workout.get("start_time") or ""
            if since and start_time < since:
                break  # API is newest-first; everything after this is older
            all_workouts.append(workout)

    # Reverse so older workouts are processed first (required for correct
    # performance tagging — each set compares against prior sessions).
    all_workouts.sort(key=lambda w: w.get("start_time") or "")
    print(f"Processing {len(all_workouts)} workouts (oldest-first)…")

    with get_connection() as conn:
        for workout in all_workouts:
            db_id = _upsert_workout(conn, workout, user_id)
            _insert_exercises_and_sets(conn, db_id, workout, user_id)
            conn.commit()
            print(f"  ✓ {workout.get('title', 'Untitled')}  [{workout['id']}]")

    update_last_synced_at(user_id, "strength", "hevy")
    print("Sync complete.")


if __name__ == "__main__":
    sync_workouts()
