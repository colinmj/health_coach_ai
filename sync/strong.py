"""Sync Strong app workout CSV export into PostgreSQL.

Run:
    python -m sync.strong path/to/strong.csv

Each run is idempotent — existing workouts are replaced (exercises and sets
are cascade-deleted then re-inserted so data stays fresh).

Strong CSV columns (semicolon-separated):
    Date, Workout Name, Duration, Exercise Name, Set Order, Weight, Reps,
    Distance, Seconds, Notes, Workout Notes, RPE
"""

import csv
import io
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

from db.schema import get_connection, get_local_user_id, init_db

load_dotenv()


# ---------------------------------------------------------------------------
# 1RM & performance tagging (mirrors sync/hevy.py logic)
# ---------------------------------------------------------------------------

def _epley_1rm(weight_kg: float | None, reps: int | None) -> float | None:
    if not weight_kg or not reps:
        return None
    if reps == 1:
        return round(weight_kg, 2)
    return round(weight_kg * (1 + reps / 30), 2)


def _prev_best_1rm(
    conn: psycopg.Connection[dict[str, Any]],
    exercise_title: str,
    before_started_at: str,
    user_id: int,
) -> float | None:
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm) AS best
        FROM strong_sets s
        JOIN strong_exercises e ON s.exercise_id = e.id
        JOIN strong_workouts w  ON e.workout_id  = w.id
        WHERE e.title = %s
          AND w.started_at < %s
          AND w.user_id = %s
        """,
        (exercise_title, before_started_at, user_id),
    ).fetchone()
    return row["best"] if row and row["best"] is not None else None


def _all_time_best_1rm(
    conn: psycopg.Connection[dict[str, Any]],
    exercise_title: str,
    exclude_external_id: str,
    user_id: int,
) -> float | None:
    row = conn.execute(
        """
        SELECT MAX(s.estimated_1rm) AS best
        FROM strong_sets s
        JOIN strong_exercises e ON s.exercise_id = e.id
        JOIN strong_workouts w  ON e.workout_id  = w.id
        WHERE e.title = %s
          AND w.external_id != %s
          AND w.user_id = %s
        """,
        (exercise_title, exclude_external_id, user_id),
    ).fetchone()
    return row["best"] if row and row["best"] is not None else None


def _performance_tag(
    estimated_1rm: float | None,
    prev_best: float | None,
    all_time_best: float | None,
) -> str | None:
    if estimated_1rm is None:
        return None
    if all_time_best is None or estimated_1rm > all_time_best:
        return "PR"
    if prev_best is None:
        return "PR"
    diff = (estimated_1rm - prev_best) / prev_best if prev_best else 0
    if diff > 0.025:
        return "Better"
    if diff < -0.025:
        return "Worse"
    return "Neutral"


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

_LBS_TO_KG = 0.453592


def _to_float(val: str) -> float | None:
    val = val.strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


def _to_int(val: str) -> int | None:
    f = _to_float(val)
    return int(f) if f is not None else None


def _parse_duration_to_seconds(val: str) -> int | None:
    """Parse Strong duration string (e.g. '1h 30m', '45m') to seconds."""
    val = val.strip()
    if not val:
        return None
    total = 0
    for match in re.finditer(r"(\d+)\s*([hHmMsS])", val):
        n = int(match.group(1))
        unit = match.group(2).lower()
        if unit == "h":
            total += n * 3600
        elif unit == "m":
            total += n * 60
        elif unit == "s":
            total += n
    return total if total else None


def _parse_csv(content: bytes) -> list[dict]:
    """Decode and sniff the CSV dialect (comma or semicolon separator)."""
    text = content.decode("utf-8-sig", errors="replace")
    first_line = text.split("\n")[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=sep)
    return list(reader)


# ---------------------------------------------------------------------------
# Main sync function (called by API upload endpoint and CLI)
# ---------------------------------------------------------------------------

def sync_strong_csv(content: bytes, user_id: int, conn: psycopg.Connection[dict[str, Any]]) -> int:
    """Parse Strong CSV and upsert into strong_workouts / exercises / sets.

    Returns the number of workouts imported.
    """
    rows = _parse_csv(content)
    if not rows:
        raise ValueError("CSV is empty or could not be parsed")

    required = {"Date", "Workout Name", "Exercise Name"}
    missing = required - set(rows[0].keys())
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Detect weight unit from header or assume lbs (Strong default)
    first_row = rows[0]
    weight_header = next((k for k in first_row if "weight" in k.lower()), "Weight")
    unit_is_lbs = "(lbs)" in weight_header.lower() or "(lb)" in weight_header.lower()

    # Group rows into workouts: {(date_str, workout_name): [rows]}
    workouts: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        key = (row.get("Date", "").strip(), row.get("Workout Name", "").strip())
        if key[0] and key[1]:
            workouts[key].append(row)

    if not workouts:
        raise ValueError("No valid workout rows found in CSV")

    # Process workouts oldest-first so performance tags are accurate
    sorted_workouts = sorted(workouts.items(), key=lambda x: x[0][0])

    imported = 0
    for (date_str, workout_name), workout_rows in sorted_workouts:
        # Parse timestamp — Strong format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DD"
        started_at = date_str if len(date_str) > 10 else f"{date_str} 00:00:00"
        external_id = re.sub(r"[^a-z0-9_]", "_", f"{date_str}_{workout_name}".lower())

        duration_seconds = _parse_duration_to_seconds(
            workout_rows[0].get("Duration", "") or workout_rows[0].get("Workout Duration", "")
        )

        # Upsert workout (cascade delete children so we re-insert fresh)
        existing = conn.execute(
            "SELECT id FROM strong_workouts WHERE user_id = %s AND external_id = %s",
            (user_id, external_id),
        ).fetchone()

        if existing:
            workout_db_id = existing["id"]
            conn.execute(
                "DELETE FROM strong_exercises WHERE workout_id = %s",
                (workout_db_id,),
            )
            conn.execute(
                """
                UPDATE strong_workouts
                SET title=%s, started_at=%s, duration_seconds=%s
                WHERE id=%s
                """,
                (workout_name, started_at, duration_seconds, workout_db_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO strong_workouts (user_id, external_id, title, started_at, duration_seconds)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (user_id, external_id, workout_name, started_at, duration_seconds),
            )
            workout_db_id = conn.execute(
                "SELECT id FROM strong_workouts WHERE user_id = %s AND external_id = %s",
                (user_id, external_id),
            ).fetchone()["id"]

        # Group sets by exercise
        exercises: dict[str, list[dict]] = defaultdict(list)
        for row in workout_rows:
            ex_name = row.get("Exercise Name", "").strip()
            if ex_name:
                exercises[ex_name].append(row)

        for ex_index, (exercise_title, set_rows) in enumerate(exercises.items()):
            notes = set_rows[0].get("Notes", "").strip() or None
            conn.execute(
                """
                INSERT INTO strong_exercises (workout_id, title, notes, exercise_index)
                VALUES (%s, %s, %s, %s)
                """,
                (workout_db_id, exercise_title, notes, ex_index),
            )
            exercise_db_id = conn.execute(
                "SELECT id FROM strong_exercises WHERE workout_id = %s AND title = %s AND exercise_index = %s",
                (workout_db_id, exercise_title, ex_index),
            ).fetchone()["id"]

            # Lookup previous bests for performance tagging
            prev_best = _prev_best_1rm(conn, exercise_title, started_at, user_id)
            all_time_best = _all_time_best_1rm(conn, exercise_title, external_id, user_id)

            for set_row in sorted(set_rows, key=lambda r: _to_int(r.get("Set Order", "0")) or 0):
                set_index = _to_int(set_row.get("Set Order"))
                reps = _to_int(set_row.get("Reps"))
                rpe = _to_float(set_row.get("RPE"))
                duration_s = _to_int(set_row.get("Seconds"))
                distance_m = _to_float(set_row.get("Distance"))

                raw_weight = _to_float(set_row.get("Weight") or set_row.get(weight_header, ""))
                if raw_weight is not None and unit_is_lbs:
                    weight_kg = round(raw_weight * _LBS_TO_KG, 3)
                else:
                    weight_kg = raw_weight

                estimated_1rm = _epley_1rm(weight_kg, reps)
                tag = _performance_tag(estimated_1rm, prev_best, all_time_best)

                # Update prev_best for subsequent sets in the same exercise
                if estimated_1rm is not None:
                    if prev_best is None or estimated_1rm > prev_best:
                        prev_best = estimated_1rm

                conn.execute(
                    """
                    INSERT INTO strong_sets
                        (exercise_id, set_index, weight_kg, reps, duration_seconds,
                         distance_meters, rpe, estimated_1rm, performance_tag)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (exercise_db_id, set_index, weight_kg, reps, duration_s,
                     distance_m, rpe, estimated_1rm, tag),
                )

        imported += 1

    return imported


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m sync.strong <path/to/strong.csv>")
        sys.exit(1)

    init_db()
    user_id = get_local_user_id()
    content = Path(sys.argv[1]).read_bytes()

    with get_connection() as conn:
        count = sync_strong_csv(content, user_id, conn)
        conn.commit()

    print(f"Strong sync complete: {count} workouts imported.")


if __name__ == "__main__":
    main()
