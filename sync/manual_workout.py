"""Parse and persist manually-logged workouts.

Pipeline:
  1. parse_workout_input  — sends text or image to Claude and returns structured JSON
  2. resolve_or_create_template — maps an exercise name to a template row (or creates one)
  3. save_manual_workout  — inserts workout/exercise/set rows with 1RM + performance tagging
"""

import base64
import json
import os
import time
from datetime import date

import anthropic

from sync.utils import epley_1rm, tag_performance

_PARSE_PROMPT = """You are a fitness data extractor. Extract the workout details from the provided text or image.

Return ONLY a valid JSON object with this exact shape — no prose, no markdown fences:
{{
  "title": "<workout title or null>",
  "date": "<YYYY-MM-DD or today's date if not specified>",
  "exercises": [
    {{
      "name": "<exercise name>",
      "sets": [
        {{
          "reps": <integer or null>,
          "weight_kg": <float in kg or null>,
          "rpe": <float 1-10 or null>,
          "set_type": "normal"
        }}
      ]
    }}
  ],
  "warnings": ["<any ambiguities or assumptions made>"]
}}

Rules:
- Convert all weights to kilograms: 1 lb = 0.453592 kg
- If weight is in lbs or pounds, convert to kg
- Unknown values must be null — never guess
- If no date is detected use today's date: {today}
- set_type should be "normal" unless clearly indicated as warmup, dropset, or failure
- Round weight_kg to 2 decimal places"""


def parse_workout_input(
    text: str | None,
    image_bytes: bytes | None,
    user_units: str = "metric",
) -> dict:
    """Call Claude to extract structured workout JSON from free-text or an image.

    Returns a dict with keys: title, date, exercises, warnings.
    Each exercise has: name, sets (list of {reps, weight_kg, rpe, set_type}).
    Returns {"exercises": [], "warnings": ["Could not parse workout"]} on failure.
    """
    today = date.today().isoformat()
    prompt_text = _PARSE_PROMPT.format(today=today)

    content: list[dict] = []

    if image_bytes is not None:
        b64 = base64.standard_b64encode(image_bytes).decode()
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            },
        })

    if text:
        content.append({"type": "text", "text": f"Workout notes:\n{text}"})

    content.append({"type": "text", "text": prompt_text})

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    _MAX_RETRIES = 3
    for attempt in range(_MAX_RETRIES):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1024,
                messages=[{"role": "user", "content": content}],
            )
            break
        except anthropic._exceptions.OverloadedError:
            if attempt == _MAX_RETRIES - 1:
                return {"exercises": [], "warnings": ["AI service is temporarily overloaded. Please try again."]}
            time.sleep(2 ** attempt)

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"exercises": [], "warnings": ["Could not parse workout"]}

    # Ensure required keys are present
    parsed.setdefault("title", None)
    parsed.setdefault("date", today)
    parsed.setdefault("exercises", [])
    parsed.setdefault("warnings", [])

    return parsed


_FUZZY_THRESHOLD = 0.3  # pg_trgm similarity threshold (0–1); tune if too aggressive


def resolve_or_create_template(conn, exercise_name: str, user_id: int | None = None) -> str:
    """Return the exercises.id (UUID) for a given exercise name.

    Resolution order:
      1. Case-insensitive exact match on exercises.name
      2. Case-insensitive match against any element of exercises.aliases
      3. pg_trgm fuzzy similarity match on name (handles abbreviations/OCR noise)
      4. Not found → insert a new row with source='user' and return its id

    Returns a UUID string.
    """
    name = exercise_name.strip()

    # 1. Exact name match (case-insensitive)
    row = conn.execute(
        "SELECT id FROM exercises WHERE name ILIKE %s LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        return str(row["id"])

    # 2. Alias match (exact, case-insensitive)
    row = conn.execute(
        "SELECT id FROM exercises WHERE %s ILIKE ANY(aliases) LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        return str(row["id"])

    # 3. Fuzzy match on name using trigram similarity
    row = conn.execute(
        """
        SELECT id, similarity(name, %s::text) AS sim
        FROM exercises
        WHERE similarity(name, %s::text) >= %s
        ORDER BY sim DESC
        LIMIT 1
        """,
        (name, name, _FUZZY_THRESHOLD),
    ).fetchone()
    if row:
        return str(row["id"])

    # 4. Create user-contributed exercise
    new_row = conn.execute(
        """
        INSERT INTO exercises (id, name, aliases, muscle_group, muscles_targeted, source, created_by)
        VALUES (gen_random_uuid(), %s, %s, %s, %s, 'user', %s)
        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
        RETURNING id
        """,
        (name, [], "Other", [], user_id),
    ).fetchone()
    assert new_row is not None
    return str(new_row["id"])


def save_manual_workout(conn, user_id: int, parsed: dict) -> int:
    """Insert a parsed workout into manual_workouts/exercises/sets.

    Computes estimated_1rm (Epley) and performance_tag for each set using
    baselines from previously committed manual workout rows.
    Returns the new manual_workouts.id.
    """
    workout_date = parsed.get("date") or date.today().isoformat()
    # Interpret the date as midnight UTC for start_time
    start_time = f"{workout_date}T00:00:00+00:00"

    workout_row = conn.execute(
        """
        INSERT INTO manual_workouts (user_id, title, notes, start_time)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (user_id, parsed.get("title"), parsed.get("notes"), start_time),
    ).fetchone()
    assert workout_row is not None
    workout_id: int = workout_row["id"]

    for idx, ex in enumerate(parsed.get("exercises", [])):
        template_id = resolve_or_create_template(conn, ex.get("name", "Unknown"), user_id)

        exercise_row = conn.execute(
            """
            INSERT INTO manual_exercises
                (workout_id, exercise_id, title, notes, exercise_index)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (workout_id, template_id, ex.get("name", "Unknown"), ex.get("notes"), idx),
        ).fetchone()
        assert exercise_row is not None
        exercise_id: int = exercise_row["id"]

        # Baselines for performance tagging — only already-committed rows
        prev_row = conn.execute(
            """
            SELECT MAX(s.estimated_1rm) AS best
            FROM manual_sets s
            JOIN manual_exercises e ON s.exercise_id = e.id
            JOIN manual_workouts w ON e.workout_id = w.id
            WHERE e.exercise_id = %s
              AND w.start_time < %s
              AND w.user_id = %s
            """,
            (template_id, start_time, user_id),
        ).fetchone()
        prev_best: float | None = prev_row["best"] if prev_row and prev_row["best"] is not None else None

        all_time_row = conn.execute(
            """
            SELECT MAX(s.estimated_1rm) AS best
            FROM manual_sets s
            JOIN manual_exercises e ON s.exercise_id = e.id
            JOIN manual_workouts w ON e.workout_id = w.id
            WHERE e.exercise_id = %s
              AND w.user_id = %s
              AND w.id != %s
            """,
            (template_id, user_id, workout_id),
        ).fetchone()
        all_time_best: float | None = (
            all_time_row["best"] if all_time_row and all_time_row["best"] is not None else None
        )

        for set_idx, s in enumerate(ex.get("sets", [])):
            weight_kg = s.get("weight_kg")
            reps = s.get("reps")
            e1rm = epley_1rm(weight_kg, reps)
            perf = tag_performance(e1rm, prev_best, all_time_best)

            conn.execute(
                """
                INSERT INTO manual_sets
                    (exercise_id, set_index, set_type, weight_kg, reps, rpe, estimated_1rm, performance_tag)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    exercise_id,
                    set_idx,
                    s.get("set_type", "normal"),
                    weight_kg,
                    reps,
                    s.get("rpe"),
                    e1rm,
                    perf,
                ),
            )

    return workout_id
