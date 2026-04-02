"""Analytics functions for form analysis progression and strength correlation.

Queries the form_analyses table and joins with hevy_exercises/hevy_sets to
surface how technique quality changes over time and whether it predicts
strength improvements.

All functions return list[dict] for consumption by agent tools.
"""

import json

from db.schema import get_connection


def get_form_progression(user_id: int, exercise_name: str) -> list[dict]:
    """Return every form session for an exercise in chronological order.

    Attaches the nearest Hevy strength session best 1RM (within 14 days)
    alongside each form entry so the agent can correlate technique ratings
    with strength at that point in time.

    Each dict has:
        video_date                  (str, ISO date)
        overall_rating              (str: 'good' | 'needs_work' | 'safety_concern')
        findings                    (list of str)
        cues                        (list of str)
        recovery_score_day_of       (float | None)
        nearest_strength_date       (str | None)
        session_best_1rm_kg         (float | None)
        strength_session_day_offset (int | None — negative = before video, positive = after)

    Returns an empty list if no form analyses exist for the exercise.
    exercise_name must match the slug stored in form_analyses (e.g. "deadlift",
    "barbell_squat", "bench_press").
    """
    sql = """
        WITH exercise_name_map AS (
            -- Normalise hevy exercise titles to slug form for matching
            -- e.g. "Deadlift (Barbell)" -> "deadlift", "Barbell Squat" -> "barbell_squat"
            SELECT
                e.id            AS exercise_id,
                w.start_time    AS workout_time,
                w.start_time::date AS workout_date,
                REGEXP_REPLACE(
                    LOWER(TRIM(REGEXP_REPLACE(e.title, '\s*\(.*?\)\s*', '', 'g'))),
                    '[\s\-]+', '_', 'g'
                ) AS normalized_name
            FROM hevy_exercises e
            JOIN hevy_workouts w ON e.workout_id = w.id
            WHERE w.user_id = %s
        ),
        strength_sessions AS (
            -- Best 1RM per hevy session for the target exercise slug
            SELECT
                enm.workout_date,
                MAX(s.estimated_1rm) AS session_best_1rm_kg
            FROM exercise_name_map enm
            JOIN hevy_sets s ON s.exercise_id = enm.exercise_id
            WHERE enm.normalized_name = %s
              AND s.estimated_1rm IS NOT NULL
              AND s.set_type NOT IN ('warmup', 'dropset')
            GROUP BY enm.workout_date
        ),
        form_sessions AS (
            SELECT
                video_date,
                overall_rating,
                findings,
                cues,
                recovery_score_day_of
            FROM form_analyses
            WHERE user_id = %s
              AND exercise_name = %s
            ORDER BY video_date
        ),
        nearest_strength AS (
            -- For each form session find the strength session with smallest absolute
            -- day offset within a 14-day window (prefer closer; ties go to later date)
            SELECT DISTINCT ON (fs.video_date)
                fs.video_date,
                ss.workout_date    AS nearest_strength_date,
                ss.session_best_1rm_kg,
                (ss.workout_date - fs.video_date) AS day_offset
            FROM form_sessions fs
            JOIN strength_sessions ss
                ON ABS(ss.workout_date - fs.video_date) <= 14
            ORDER BY fs.video_date, ABS(ss.workout_date - fs.video_date), ss.workout_date DESC
        )
        SELECT
            fs.video_date,
            fs.overall_rating,
            fs.findings,
            fs.cues,
            fs.recovery_score_day_of,
            ns.nearest_strength_date,
            ns.session_best_1rm_kg,
            ns.day_offset          AS strength_session_day_offset
        FROM form_sessions fs
        LEFT JOIN nearest_strength ns ON ns.video_date = fs.video_date
        ORDER BY fs.video_date
    """
    params = [user_id, exercise_name, user_id, exercise_name]

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["video_date"] = str(d["video_date"])
        d["nearest_strength_date"] = (
            str(d["nearest_strength_date"]) if d["nearest_strength_date"] is not None else None
        )
        d["session_best_1rm_kg"] = (
            float(d["session_best_1rm_kg"]) if d["session_best_1rm_kg"] is not None else None
        )
        d["strength_session_day_offset"] = (
            int(d["strength_session_day_offset"])
            if d["strength_session_day_offset"] is not None
            else None
        )
        d["recovery_score_day_of"] = (
            float(d["recovery_score_day_of"])
            if d["recovery_score_day_of"] is not None
            else None
        )
        # findings / cues come from JSONB — psycopg returns them as Python objects;
        # if somehow stored as a raw string, parse it.
        for field in ("findings", "cues"):
            val = d.get(field)
            if isinstance(val, str):
                try:
                    d[field] = json.loads(val)
                except (ValueError, TypeError):
                    d[field] = [val]
            elif val is None:
                d[field] = []
        result.append(d)

    return result


def get_form_vs_strength(user_id: int, exercise_name: str) -> list[dict]:
    """Group form sessions by overall_rating and compare average 1RM in the 30 days after.

    Answers: "do my squat numbers improve after good-form sessions compared to
    needs_work sessions?"

    Each dict has:
        overall_rating          (str: 'good' | 'needs_work' | 'safety_concern')
        session_count           (int — number of form sessions with that rating)
        avg_followup_1rm_kg     (float | None — mean of best 1RM across followup sessions)
        avg_peak_followup_1rm_kg (float | None — mean of the peak 1RM seen across followup sessions)
        avg_recovery_score      (float | None — mean recovery on the days of form sessions)
        total_followup_sessions (int — total hevy sessions found within 30 days after)

    Returns an empty list if no form analyses exist for the exercise.
    """
    sql = """
        WITH exercise_name_map AS (
            SELECT
                e.id            AS exercise_id,
                w.start_time::date AS workout_date,
                REGEXP_REPLACE(
                    LOWER(TRIM(REGEXP_REPLACE(e.title, '\s*\(.*?\)\s*', '', 'g'))),
                    '[\s\-]+', '_', 'g'
                ) AS normalized_name
            FROM hevy_exercises e
            JOIN hevy_workouts w ON e.workout_id = w.id
            WHERE w.user_id = %s
        ),
        strength_sessions AS (
            SELECT
                enm.workout_date,
                MAX(s.estimated_1rm) AS session_best_1rm_kg
            FROM exercise_name_map enm
            JOIN hevy_sets s ON s.exercise_id = enm.exercise_id
            WHERE enm.normalized_name = %s
              AND s.estimated_1rm IS NOT NULL
              AND s.set_type NOT IN ('warmup', 'dropset')
            GROUP BY enm.workout_date
        ),
        form_with_followup AS (
            -- For each form session, collect all strength sessions in the 30 days after
            SELECT
                fa.overall_rating,
                fa.recovery_score_day_of,
                ss.session_best_1rm_kg  AS followup_1rm_kg
            FROM form_analyses fa
            LEFT JOIN strength_sessions ss
                ON ss.workout_date > fa.video_date
               AND ss.workout_date <= fa.video_date + INTERVAL '30 days'
            WHERE fa.user_id = %s
              AND fa.exercise_name = %s
        )
        SELECT
            overall_rating,
            COUNT(DISTINCT overall_rating) OVER (PARTITION BY overall_rating)   AS session_count,
            ROUND(AVG(followup_1rm_kg)::numeric, 2)                             AS avg_followup_1rm_kg,
            ROUND(MAX(followup_1rm_kg)::numeric, 2)                             AS avg_peak_followup_1rm_kg,
            ROUND(AVG(recovery_score_day_of)::numeric, 1)                       AS avg_recovery_score,
            COUNT(followup_1rm_kg)                                               AS total_followup_sessions
        FROM form_with_followup
        GROUP BY overall_rating
        ORDER BY overall_rating
    """
    # Fix: session_count via COUNT DISTINCT OVER is tricky — use a simpler approach
    # Replace the query above with a cleaner version using two CTEs
    sql = """
        WITH exercise_name_map AS (
            SELECT
                e.id            AS exercise_id,
                w.start_time::date AS workout_date,
                REGEXP_REPLACE(
                    LOWER(TRIM(REGEXP_REPLACE(e.title, '\s*\(.*?\)\s*', '', 'g'))),
                    '[\s\-]+', '_', 'g'
                ) AS normalized_name
            FROM hevy_exercises e
            JOIN hevy_workouts w ON e.workout_id = w.id
            WHERE w.user_id = %s
        ),
        strength_sessions AS (
            SELECT
                enm.workout_date,
                MAX(s.estimated_1rm) AS session_best_1rm_kg
            FROM exercise_name_map enm
            JOIN hevy_sets s ON s.exercise_id = enm.exercise_id
            WHERE enm.normalized_name = %s
              AND s.estimated_1rm IS NOT NULL
              AND s.set_type NOT IN ('warmup', 'dropset')
            GROUP BY enm.workout_date
        ),
        form_base AS (
            SELECT
                id              AS form_id,
                overall_rating,
                recovery_score_day_of,
                video_date
            FROM form_analyses
            WHERE user_id = %s
              AND exercise_name = %s
        ),
        form_with_followup AS (
            SELECT
                fb.form_id,
                fb.overall_rating,
                fb.recovery_score_day_of,
                ss.session_best_1rm_kg AS followup_1rm_kg
            FROM form_base fb
            LEFT JOIN strength_sessions ss
                ON ss.workout_date > fb.video_date
               AND ss.workout_date <= fb.video_date + INTERVAL '30 days'
        )
        SELECT
            overall_rating,
            COUNT(DISTINCT form_id)                          AS session_count,
            ROUND(AVG(followup_1rm_kg)::numeric, 2)          AS avg_followup_1rm_kg,
            ROUND(MAX(followup_1rm_kg)::numeric, 2)          AS avg_peak_followup_1rm_kg,
            ROUND(AVG(recovery_score_day_of)::numeric, 1)    AS avg_recovery_score,
            COUNT(followup_1rm_kg)                           AS total_followup_sessions
        FROM form_with_followup
        GROUP BY overall_rating
        ORDER BY overall_rating
    """
    params = [user_id, exercise_name, user_id, exercise_name]

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        d["avg_followup_1rm_kg"] = (
            float(d["avg_followup_1rm_kg"]) if d["avg_followup_1rm_kg"] is not None else None
        )
        d["avg_peak_followup_1rm_kg"] = (
            float(d["avg_peak_followup_1rm_kg"])
            if d["avg_peak_followup_1rm_kg"] is not None
            else None
        )
        d["avg_recovery_score"] = (
            float(d["avg_recovery_score"]) if d["avg_recovery_score"] is not None else None
        )
        d["session_count"] = int(d["session_count"])
        d["total_followup_sessions"] = (
            int(d["total_followup_sessions"]) if d["total_followup_sessions"] is not None else 0
        )
        result.append(d)

    return result
