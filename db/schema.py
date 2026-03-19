import sqlite3
from pathlib import Path

DB_PATH = Path("health_coach.db")

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS hevy_workouts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    hevy_id     TEXT    UNIQUE NOT NULL,
    title       TEXT,
    start_time  TEXT,
    end_time    TEXT,
    synced_at   TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS hevy_exercises (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id           INTEGER NOT NULL REFERENCES hevy_workouts(id) ON DELETE CASCADE,
    exercise_template_id TEXT,
    title                TEXT NOT NULL,
    notes                TEXT,
    exercise_index       INTEGER
);

CREATE TABLE IF NOT EXISTS hevy_sets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    exercise_id      INTEGER NOT NULL REFERENCES hevy_exercises(id) ON DELETE CASCADE,
    set_index        INTEGER,
    set_type         TEXT,
    weight_kg        REAL,
    reps             INTEGER,
    duration_seconds INTEGER,
    distance_meters  REAL,
    rpe              REAL,
    estimated_1rm    REAL,
    performance_tag  TEXT    -- PR | Better | Neutral | Worse
);

CREATE VIEW IF NOT EXISTS v_exercise_prs AS
WITH working_sets AS (
    SELECT
        s.estimated_1rm, s.weight_kg, s.reps,
        e.exercise_template_id, e.title AS exercise_title,
        w.hevy_id AS workout_hevy_id, w.title AS workout_title, w.start_time
    FROM hevy_sets s
    JOIN hevy_exercises e ON s.exercise_id = e.id
    JOIN hevy_workouts  w ON e.workout_id  = w.id
    WHERE s.estimated_1rm IS NOT NULL
      AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY exercise_template_id
        ORDER BY estimated_1rm DESC, weight_kg DESC, start_time ASC
    ) AS rn
    FROM working_sets
)
SELECT
    exercise_template_id, exercise_title,
    estimated_1rm  AS pr_1rm_kg,
    weight_kg      AS pr_weight_kg,
    reps           AS pr_reps,
    workout_hevy_id, workout_title,
    start_time     AS pr_date
FROM ranked WHERE rn = 1
ORDER BY pr_1rm_kg DESC;

CREATE VIEW IF NOT EXISTS v_workout_1rm AS
WITH working_sets AS (
    SELECT
        s.estimated_1rm, s.weight_kg, s.reps, s.set_index,
        e.exercise_template_id, e.title AS exercise_title,
        w.id AS workout_id, w.hevy_id AS workout_hevy_id,
        w.title AS workout_title, w.start_time
    FROM hevy_sets s
    JOIN hevy_exercises e ON s.exercise_id = e.id
    JOIN hevy_workouts  w ON e.workout_id  = w.id
    WHERE s.estimated_1rm IS NOT NULL
      AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (
        PARTITION BY workout_id, exercise_template_id
        ORDER BY estimated_1rm DESC, weight_kg DESC, set_index ASC
    ) AS rn
    FROM working_sets
)
SELECT
    workout_hevy_id, workout_title,
    start_time            AS workout_date,
    exercise_template_id, exercise_title,
    estimated_1rm         AS session_best_1rm_kg,
    weight_kg             AS best_set_weight_kg,
    reps                  AS best_set_reps
FROM ranked WHERE rn = 1
ORDER BY exercise_template_id, start_time;

CREATE TABLE IF NOT EXISTS recovery (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    whoop_cycle_id       TEXT    UNIQUE NOT NULL,
    date                 TEXT    NOT NULL,  -- YYYY-MM-DD, for cross-domain joins
    source               TEXT    NOT NULL DEFAULT 'whoop',
    score_state          TEXT,              -- SCORED | PENDING_SCORE | UNSCORABLE
    recovery_score       REAL,
    hrv_rmssd_milli      REAL,
    resting_heart_rate   REAL,
    spo2_percentage      REAL,
    skin_temp_celsius    REAL,
    synced_at            TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sleep (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    whoop_sleep_id                TEXT    UNIQUE NOT NULL,
    whoop_cycle_id                TEXT,   -- links to recovery.whoop_cycle_id
    date                          TEXT    NOT NULL,  -- DATE(start), YYYY-MM-DD
    source                        TEXT    NOT NULL DEFAULT 'whoop',
    is_nap                        INTEGER NOT NULL DEFAULT 0,
    score_state                   TEXT,
    start_time                    TEXT,
    end_time                      TEXT,
    total_in_bed_time_milli       INTEGER,
    total_awake_time_milli        INTEGER,
    total_light_sleep_milli       INTEGER,
    total_slow_wave_sleep_milli   INTEGER,
    total_rem_sleep_milli         INTEGER,
    disturbance_count             INTEGER,
    sleep_performance_percentage  REAL,
    sleep_efficiency_percentage   REAL,
    respiratory_rate              REAL,
    synced_at                     TEXT    DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS body_measurements (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    withings_group_id INTEGER UNIQUE NOT NULL,   -- grpid from API
    measured_at       TEXT    NOT NULL,           -- ISO-8601 from Unix epoch
    date              TEXT    NOT NULL,           -- YYYY-MM-DD for cross-domain joins
    source            TEXT    NOT NULL DEFAULT 'withings',
    weight_kg         REAL,
    fat_free_mass_kg  REAL,
    fat_ratio         REAL,   -- body fat %
    fat_mass_kg       REAL,
    muscle_mass_kg    REAL,
    hydration_kg      REAL,
    bone_mass_kg      REAL,
    synced_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE VIEW IF NOT EXISTS v_workout_performance AS
SELECT
    w.hevy_id          AS workout_hevy_id,
    w.title            AS workout_title,
    DATE(w.start_time) AS workout_date,
    w.start_time,
    COUNT(s.id)        AS total_sets,
    SUM(CASE WHEN s.performance_tag = 'PR'      THEN 1 ELSE 0 END) AS pr_sets,
    SUM(CASE WHEN s.performance_tag = 'Better'  THEN 1 ELSE 0 END) AS better_sets,
    SUM(CASE WHEN s.performance_tag = 'Neutral' THEN 1 ELSE 0 END) AS neutral_sets,
    SUM(CASE WHEN s.performance_tag = 'Worse'   THEN 1 ELSE 0 END) AS worse_sets,
    ROUND(AVG(CASE
        WHEN s.performance_tag = 'PR'      THEN 3.0
        WHEN s.performance_tag = 'Better'  THEN 2.0
        WHEN s.performance_tag = 'Neutral' THEN 1.0
        WHEN s.performance_tag = 'Worse'   THEN 0.0
    END), 2) AS performance_score,
    CASE
        WHEN MAX(CASE WHEN s.performance_tag = 'PR'     THEN 3 ELSE 0 END) = 3 THEN 'PR'
        WHEN MAX(CASE WHEN s.performance_tag = 'Better' THEN 2 ELSE 0 END) = 2 THEN 'Better'
        WHEN MAX(CASE WHEN s.performance_tag = 'Worse'  THEN 1 ELSE 0 END) = 1 THEN 'Neutral'
        ELSE 'Worse'
    END AS best_tag
FROM hevy_workouts w
JOIN hevy_exercises e ON e.workout_id = w.id
JOIN hevy_sets s ON s.exercise_id = e.id
WHERE (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
GROUP BY w.id
ORDER BY w.start_time DESC;
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(_CREATE_TABLES)
