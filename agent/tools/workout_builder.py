"""Workout Builder agent tools.

Covers: training profile lookup, program persistence, Hevy routine sync,
and block management (Advanced/Elite users only).
"""

import json
import re
from datetime import date, datetime, timedelta, timezone

from langchain_core.tools import tool

from clients.hevy import HevyClient
from db.schema import get_connection, get_request_user_id
from sync.utils import get_integration_tokens

_VALID_GOAL_TYPES = {"cut", "bulk", "recomp", "strength", "athletic"}
_VALID_PROGRAM_TYPES = {"hevy", "manual"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_reps(reps_value) -> int:
    """Parse reps as int, range string ('6-8'), or plain string. Returns midpoint for ranges."""
    if isinstance(reps_value, int):
        return reps_value
    s = str(reps_value).strip()
    m = re.match(r"^(\d+)\s*[-–]\s*(\d+)$", s)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2
    try:
        return int(s)
    except ValueError:
        return 8


def _build_hevy_exercise(ex: dict) -> dict:
    """Convert a program exercise dict to a Hevy routine exercise object."""
    set_count = int(ex.get("sets", 3))
    reps = _parse_reps(ex.get("reps", 8))
    rest = int(ex.get("rest_seconds", 90))

    sets = [
        {
            "type": "normal",
            "weight_kg": None,
            "reps": reps,
            "duration_seconds": None,
            "distance_meters": None,
        }
        for _ in range(set_count)
    ]

    return {
        "exercise_template_id": ex.get("exercise_template_id", ""),
        "superset_id": None,
        "rest_seconds": rest,
        "notes": ex.get("notes", ""),
        "sets": sets,
    }


def _db_create_training_block(
    conn,
    user_id: int,
    name: str,
    goal: str,
    start: date,
    end: date | None,
    notes: str | None,
) -> dict:
    """Close any open block, insert a new one, return the inserted row as dict."""
    prev_end = start - timedelta(days=1)
    conn.execute(
        "UPDATE training_blocks SET end_date = %s WHERE user_id = %s AND end_date IS NULL",
        (prev_end, user_id),
    )
    row = conn.execute(
        """
        INSERT INTO training_blocks (user_id, name, goal, start_date, end_date, notes)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, name, goal, start_date, end_date, notes, created_at
        """,
        (user_id, name, goal, start, end, notes),
    ).fetchone()
    result = dict(row)
    result["is_active"] = result["end_date"] is None
    return result


def _query_block_performance(conn, user_id: int, start: date, end: date | None) -> dict:
    """Run the three block-performance queries and return aggregated results."""
    date_filter = "w.start_time::date >= %s AND w.start_time::date <= COALESCE(%s, CURRENT_DATE)"
    base_params = (user_id, start, end)

    stats = conn.execute(
        f"""
        SELECT
            COUNT(DISTINCT w.id)                                           AS workout_count,
            COUNT(s.id)                                                    AS total_sets,
            COUNT(s.id) FILTER (WHERE s.performance_tag = 'PR')           AS pr_sets,
            COUNT(s.id) FILTER (WHERE s.performance_tag = 'Better')       AS better_sets,
            COUNT(s.id) FILTER (WHERE s.performance_tag = 'Neutral')      AS neutral_sets,
            COUNT(s.id) FILTER (WHERE s.performance_tag = 'Worse')        AS worse_sets
        FROM hevy_workouts w
        JOIN hevy_exercises e ON e.workout_id = w.id
        JOIN hevy_sets s      ON s.exercise_id = e.id
        WHERE w.user_id = %s AND {date_filter}
        """,
        base_params,
    ).fetchone()

    top_ex = conn.execute(
        f"""
        SELECT
            e.title                                                        AS exercise_title,
            COUNT(s.id) FILTER (WHERE s.performance_tag = 'PR')           AS pr_count,
            ROUND(MAX(s.estimated_1rm)::numeric, 1)                       AS max_1rm_kg,
            ROUND(SUM(s.weight_kg * s.reps)::numeric, 1)                  AS total_volume_kg
        FROM hevy_workouts w
        JOIN hevy_exercises e ON e.workout_id = w.id
        JOIN hevy_sets s      ON s.exercise_id = e.id
        WHERE w.user_id = %s AND {date_filter}
        GROUP BY e.title
        ORDER BY pr_count DESC, total_volume_kg DESC
        LIMIT 10
        """,
        base_params,
    ).fetchall()

    weekly = conn.execute(
        f"""
        SELECT
            DATE_TRUNC('week', w.start_time)::date AS week_start,
            COUNT(DISTINCT w.id)                   AS workouts,
            COUNT(s.id)                            AS total_sets
        FROM hevy_workouts w
        JOIN hevy_exercises e ON e.workout_id = w.id
        JOIN hevy_sets s      ON s.exercise_id = e.id
        WHERE w.user_id = %s AND {date_filter}
        GROUP BY week_start
        ORDER BY week_start
        """,
        base_params,
    ).fetchall()

    return {
        "workout_count": stats["workout_count"],
        "total_sets": stats["total_sets"],
        "performance_tag_distribution": {
            "PR": stats["pr_sets"],
            "Better": stats["better_sets"],
            "Neutral": stats["neutral_sets"],
            "Worse": stats["worse_sets"],
        },
        "top_exercises": [dict(r) for r in top_ex],
        "weekly_volume_trend": [dict(r) for r in weekly],
    }


def _execute_hevy_sync(user_id: int, program_id: str) -> dict:
    """Core logic for syncing a training program to Hevy.

    Returns: {routines_created, routines_skipped, folder_id, hevy_synced_at}
    Raises ValueError if the program has type='manual' or is not found.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, name, type, blocks FROM training_programs WHERE id = %s AND user_id = %s",
            (program_id, user_id),
        ).fetchone()

    if not row:
        raise ValueError(f"Program {program_id} not found.")
    if row["type"] != "hevy":
        raise ValueError("This program is not linked to Hevy. Only programs with type='hevy' can be synced.")

    program_name = row["name"]
    blocks = row["blocks"] if isinstance(row["blocks"], list) else json.loads(row["blocks"])

    api_key, _ = get_integration_tokens(user_id, "hevy")

    with HevyClient(api_key) as client:
        existing_titles = {r.get("title", "") for r in client.get_routines()}
        folder = client.create_routine_folder(program_name)
        folder_id = folder.get("id") or folder.get("folder_id")

        routines_created = 0
        routines_skipped = 0

        for block_idx, block in enumerate(blocks):
            block_name = block.get("name", f"Block {block_idx + 1}")
            block_sessions = block.get("sessions", [])

            for session_idx, session in enumerate(block_sessions):
                day_label = session.get("day_label", f"Day {session_idx + 1}")
                routine_title = f"{program_name} — {block_name} — {day_label}"

                if routine_title in existing_titles:
                    routines_skipped += 1
                    continue

                exercises = [
                    _build_hevy_exercise(ex)
                    for ex in session.get("exercises", [])
                    if ex.get("exercise_template_id")
                ]

                client.create_routine(
                    title=routine_title,
                    folder_id=str(folder_id) if folder_id is not None else None,
                    exercises=exercises,
                )
                routines_created += 1

    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        conn.execute(
            "UPDATE training_programs SET hevy_synced_at = %s WHERE id = %s AND user_id = %s",
            (now, program_id, user_id),
        )

    return {
        "routines_created": routines_created,
        "routines_skipped": routines_skipped,
        "folder_id": str(folder_id) if folder_id is not None else None,
        "hevy_synced_at": now.isoformat(),
    }


# ---------------------------------------------------------------------------
# Program tools
# ---------------------------------------------------------------------------

@tool
def get_training_profile() -> str:
    """Return the user's training profile for workout program generation.

    Includes: training IQ level, hevy_connected bool, active goals, last 12 weeks
    of Hevy workout history (exercise names, set/rep ranges, estimated 1RMs),
    30-day recovery trend, latest body measurement, known injuries, and health conditions.

    Returns a JSON object with keys: training_iq, hevy_connected, goals,
    hevy_summary, recovery_summary, body_summary, injuries, health_conditions."""
    user_id = get_request_user_id()

    with get_connection() as conn:
        user_row = conn.execute(
            "SELECT training_iq, injuries, health_conditions FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()

        hevy_row = conn.execute(
            "SELECT 1 FROM user_integrations WHERE user_id = %s AND source = 'hevy' AND access_token IS NOT NULL",
            (user_id,),
        ).fetchone()

        goal_rows = conn.execute(
            "SELECT goal_text, domains, target_date FROM goals WHERE user_id = %s AND status = 'active' LIMIT 5",
            (user_id,),
        ).fetchall()

        hevy_rows = conn.execute(
            """
            SELECT
                e.exercise_template_id,
                e.title AS exercise_title,
                COUNT(DISTINCT w.id) AS session_count,
                ROUND(MAX(s.estimated_1rm)::numeric, 1) AS max_1rm_kg,
                ROUND(AVG(s.reps)::numeric, 1) AS avg_reps,
                ROUND(AVG(s.weight_kg)::numeric, 1) AS avg_weight_kg
            FROM hevy_workouts w
            JOIN hevy_exercises e ON e.workout_id = w.id
            JOIN hevy_sets s ON s.exercise_id = e.id
            WHERE w.user_id = %s
              AND w.start_time >= NOW() - INTERVAL '12 weeks'
              AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
            GROUP BY e.exercise_template_id, e.title
            ORDER BY session_count DESC
            LIMIT 30
            """,
            (user_id,),
        ).fetchall()

        recovery_row = conn.execute(
            """
            SELECT
                ROUND(AVG(recovery_score)::numeric, 1) AS avg_recovery,
                ROUND(AVG(hrv_rmssd_milli)::numeric, 1) AS avg_hrv,
                MIN(recovery_score) AS min_recovery,
                MAX(recovery_score) AS max_recovery
            FROM recovery
            WHERE user_id = %s AND date >= CURRENT_DATE - INTERVAL '30 days'
            """,
            (user_id,),
        ).fetchone()

        body_row = conn.execute(
            """
            SELECT weight_kg, fat_ratio, muscle_mass_kg
            FROM body_measurements
            WHERE user_id = %s
            ORDER BY measured_at DESC LIMIT 1
            """,
            (user_id,),
        ).fetchone()

    result = {
        "training_iq": user_row["training_iq"] if user_row else None,
        "injuries": user_row["injuries"] if user_row else None,
        "health_conditions": user_row["health_conditions"] if user_row else None,
        "hevy_connected": hevy_row is not None,
        "goals": [dict(r) for r in goal_rows],
        "hevy_summary": [dict(r) for r in hevy_rows],
        "recovery_summary": dict(recovery_row) if recovery_row and recovery_row["avg_recovery"] else None,
        "body_summary": dict(body_row) if body_row and body_row["weight_kg"] else None,
    }
    return json.dumps(result, default=str)


@tool
def save_training_program(
    name: str,
    goal_type: str,
    blocks_json: str,
    program_type: str = "manual",
) -> str:
    """Save a generated training program to the database.

    name: short descriptive program name (e.g. 'Upper/Lower Strength Block').
    goal_type: one of cut / bulk / recomp / strength / athletic.
    blocks_json: JSON array string — the full program structure.

    Block schema (each item in the array):
    {
      "name": "Block A — Hypertrophy",
      "duration_weeks": 4,
      "days_per_week": 4,
      "sessions": [
        {
          "day_label": "Day 1 — Upper Push",
          "exercises": [
            {
              "exercise_template_id": "...",
              "exercise_title": "Bench Press (Barbell)",
              "sets": 4,
              "reps": "6-8",
              "rest_seconds": 120,
              "notes": "RPE 8"
            }
          ]
        }
      ]
    }

    program_type: "hevy" if the user has Hevy connected; "manual" otherwise.
      Only "hevy" programs can later be synced to Hevy.

    Deactivates any currently active program before saving the new one as active.
    Returns JSON with the new program id and metadata."""
    user_id = get_request_user_id()

    try:
        blocks = json.loads(blocks_json)
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid blocks_json: {e}"})

    if goal_type not in _VALID_GOAL_TYPES:
        return json.dumps({"error": f"goal_type must be one of {sorted(_VALID_GOAL_TYPES)}"})

    if program_type not in _VALID_PROGRAM_TYPES:
        program_type = "manual"

    with get_connection() as conn:
        iq_row = conn.execute("SELECT training_iq FROM users WHERE id = %s", (user_id,)).fetchone()
        iq = iq_row["training_iq"] if iq_row else None

        conn.execute(
            "UPDATE training_programs SET is_active = FALSE WHERE user_id = %s AND is_active = TRUE",
            (user_id,),
        )

        row = conn.execute(
            """
            INSERT INTO training_programs
                (user_id, name, type, goal_type, training_iq_at_generation, blocks, is_active)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, TRUE)
            RETURNING id::text, version, created_at
            """,
            (user_id, name, program_type, goal_type, iq, json.dumps(blocks)),
        ).fetchone()

    return json.dumps({
        "program_id": row["id"],
        "version": row["version"],
        "name": name,
        "type": program_type,
        "goal_type": goal_type,
        "training_iq_at_generation": iq,
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
        "message": "Program saved and set as active.",
    })


@tool
def get_training_programs(include_inactive: bool = False) -> str:
    """Return the user's saved training programs.

    include_inactive: if False (default), returns only the active program.
    Returns a JSON list with fields: id, name, type, goal_type,
    training_iq_at_generation, is_active, hevy_synced_at, created_at,
    block_count, total_weeks."""
    user_id = get_request_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id::text,
                name,
                type,
                goal_type,
                training_iq_at_generation,
                is_active,
                hevy_synced_at,
                created_at,
                jsonb_array_length(blocks) AS block_count,
                (SELECT COALESCE(SUM((b->>'duration_weeks')::int), 0)
                 FROM jsonb_array_elements(blocks) AS b) AS total_weeks
            FROM training_programs
            WHERE user_id = %s
              AND (is_active = TRUE OR %s = TRUE)
            ORDER BY created_at DESC
            """,
            (user_id, include_inactive),
        ).fetchall()

    return json.dumps([dict(r) for r in rows], default=str)


@tool
def sync_program_to_hevy(program_id: str = "") -> str:
    """Push the user's training program to Hevy as a set of named routines.

    Creates a routine folder named after the program, then creates one routine
    per session in each block. Skips sessions whose title already exists in Hevy.

    program_id: optional UUID string. If blank, uses the currently active program.

    Only works for programs with type='hevy'. Call this only after explicit user
    confirmation that they want to sync to Hevy.

    Returns a JSON summary: routines_created, routines_skipped, folder_id, hevy_synced_at."""
    user_id = get_request_user_id()

    pid = program_id.strip()
    if not pid:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id::text FROM training_programs WHERE user_id = %s AND is_active = TRUE",
                (user_id,),
            ).fetchone()
        if not row:
            return json.dumps({"error": "No active program found. Save a program first."})
        pid = row["id"]

    try:
        result = _execute_hevy_sync(user_id, pid)
        return json.dumps(result)
    except (ValueError, RuntimeError) as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Block management tools (Advanced / Elite only)
# ---------------------------------------------------------------------------

@tool
def create_training_block(
    name: str,
    goal: str,
    start_date: str,
    end_date: str = "",
    notes: str = "",
) -> str:
    """Create a named training block for Advanced or Elite users.

    Only offer this tool to users with training_iq of 'advanced' or 'elite'.

    name: short descriptive name, e.g. 'Hypertrophy Phase 1'.
    goal: open text description of the block goal, e.g. 'Build upper body hypertrophy base'.
    start_date: YYYY-MM-DD.
    end_date: YYYY-MM-DD. If omitted, the block is open/ongoing.
    notes: optional free text.

    Automatically closes any currently open block (sets its end_date to start_date - 1 day)
    before creating the new one.

    Returns JSON with the new block id and metadata."""
    user_id = get_request_user_id()

    try:
        start = date.fromisoformat(start_date.strip())
    except ValueError:
        return json.dumps({"error": f"Invalid start_date: {start_date!r}. Use YYYY-MM-DD."})

    end: date | None = None
    if end_date.strip():
        try:
            end = date.fromisoformat(end_date.strip())
        except ValueError:
            return json.dumps({"error": f"Invalid end_date: {end_date!r}. Use YYYY-MM-DD."})

    with get_connection() as conn:
        result = _db_create_training_block(
            conn, user_id, name, goal, start, end, notes.strip() or None
        )

    return json.dumps({
        "block_id": result["id"],
        "name": result["name"],
        "goal": result["goal"],
        "start_date": result["start_date"].isoformat() if hasattr(result["start_date"], "isoformat") else result["start_date"],
        "end_date": result["end_date"].isoformat() if result["end_date"] and hasattr(result["end_date"], "isoformat") else result["end_date"],
        "is_active": result["is_active"],
        "created_at": result["created_at"].isoformat() if hasattr(result["created_at"], "isoformat") else result["created_at"],
    })


@tool
def get_training_blocks() -> str:
    """Return all training blocks for the user, ordered newest first.

    Only relevant for users with training_iq of 'advanced' or 'elite'.

    Returns a JSON list with fields: id, name, goal, start_date, end_date,
    notes, is_active, created_at."""
    user_id = get_request_user_id()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                goal,
                start_date,
                end_date,
                notes,
                end_date IS NULL AS is_active,
                created_at
            FROM training_blocks
            WHERE user_id = %s
            ORDER BY start_date DESC
            """,
            (user_id,),
        ).fetchall()

    return json.dumps([dict(r) for r in rows], default=str)


@tool
def get_block_performance(block_id: int) -> str:
    """Return training performance data for a specific training block.

    Queries all workout data that falls within the block's date range.

    Only relevant for users with training_iq of 'advanced' or 'elite'.

    block_id: integer block id from get_training_blocks().

    Returns JSON with: block metadata, workout_count, pr_count, total_sets,
    performance_tag_distribution, top_exercises (by PR count and volume),
    and weekly_volume_trend."""
    user_id = get_request_user_id()

    with get_connection() as conn:
        block = conn.execute(
            "SELECT * FROM training_blocks WHERE id = %s AND user_id = %s",
            (block_id, user_id),
        ).fetchone()

        if not block:
            return json.dumps({"error": f"Block {block_id} not found."})

        perf = _query_block_performance(conn, user_id, block["start_date"], block["end_date"])

    return json.dumps({"block": dict(block), **perf}, default=str)
