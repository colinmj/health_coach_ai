-- =============================================================================
-- Health Coach AI — PostgreSQL Schema
-- =============================================================================
-- Idempotent: safe to run multiple times (CREATE TABLE IF NOT EXISTS,
-- CREATE OR REPLACE VIEW, CREATE INDEX IF NOT EXISTS).
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Users & auth
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id            SERIAL      PRIMARY KEY,
    email         TEXT        UNIQUE NOT NULL,
    name          TEXT,
    date_of_birth DATE,
    sex           TEXT        CHECK (sex IN ('male', 'female', 'other')),
    height_cm     REAL,
    weight_kg     REAL,        -- latest value, updated by body composition sync
    fat_ratio     REAL,        -- latest value, updated by body composition sync
    units         TEXT        NOT NULL DEFAULT 'metric' CHECK (units IN ('metric', 'imperial')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Migrate: add auth + profile columns if upgrading from older schema
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sex           TEXT CHECK (sex IN ('male', 'female', 'other'));
ALTER TABLE users ADD COLUMN IF NOT EXISTS height_cm     REAL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS weight_kg     REAL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS fat_ratio     REAL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS units         TEXT NOT NULL DEFAULT 'metric' CHECK (units IN ('metric', 'imperial'));

-- One row per (user, source). Stores OAuth tokens and tracks sync state.
CREATE TABLE IF NOT EXISTS user_integrations (
    id               SERIAL      PRIMARY KEY,
    user_id          INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source           TEXT        NOT NULL,  -- 'hevy' | 'whoop' | 'withings' | 'cronometer' | etc.
    auth_type        TEXT        NOT NULL DEFAULT 'api_key' CHECK (auth_type IN ('oauth', 'api_key', 'upload')),
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at TIMESTAMPTZ,
    last_synced_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source)
);

CREATE TABLE IF NOT EXISTS user_data_imports (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    data_type  TEXT        NOT NULL,
    source     TEXT        NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, data_type)
);


-- -----------------------------------------------------------------------------
-- Strength — Hevy
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS hevy_workouts (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    hevy_id    TEXT        NOT NULL,
    title      TEXT,
    start_time TIMESTAMPTZ,
    end_time   TIMESTAMPTZ,
    synced_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, hevy_id)
);

CREATE TABLE IF NOT EXISTS hevy_exercises (
    id                   SERIAL  PRIMARY KEY,
    workout_id           INTEGER NOT NULL REFERENCES hevy_workouts(id) ON DELETE CASCADE,
    exercise_template_id TEXT,
    title                TEXT    NOT NULL,
    notes                TEXT,
    exercise_index       INTEGER
);

CREATE TABLE IF NOT EXISTS hevy_sets (
    id               SERIAL  PRIMARY KEY,
    exercise_id      INTEGER NOT NULL REFERENCES hevy_exercises(id) ON DELETE CASCADE,
    set_index        INTEGER,
    set_type         TEXT,
    weight_kg        REAL,
    reps             INTEGER,
    duration_seconds INTEGER,
    distance_meters  REAL,
    rpe              REAL,
    estimated_1rm    REAL,
    performance_tag  TEXT    -- 'PR' | 'Better' | 'Neutral' | 'Worse'
);


-- -----------------------------------------------------------------------------
-- Recovery — source-agnostic
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recovery (
    id                 SERIAL      PRIMARY KEY,
    user_id            INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    external_id        TEXT        NOT NULL,
    date               DATE        NOT NULL,
    source             TEXT        NOT NULL,
    score_state        TEXT,
    recovery_score     REAL,
    hrv_rmssd_milli    REAL,
    resting_heart_rate REAL,
    spo2_percentage    REAL,
    skin_temp_celsius  REAL,
    strain             REAL,
    daily_energy_kcal  REAL,
    synced_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source, external_id)
);

CREATE TABLE IF NOT EXISTS sleep (
    id                           SERIAL      PRIMARY KEY,
    user_id                      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    external_id                  TEXT        NOT NULL,
    date                         DATE        NOT NULL,
    source                       TEXT        NOT NULL,
    is_nap                       BOOLEAN     NOT NULL DEFAULT FALSE,
    score_state                  TEXT,
    start_time                   TIMESTAMPTZ,
    end_time                     TIMESTAMPTZ,
    total_in_bed_time_milli      INTEGER,
    total_awake_time_milli       INTEGER,
    total_light_sleep_milli      INTEGER,
    total_slow_wave_sleep_milli  INTEGER,
    total_rem_sleep_milli        INTEGER,
    disturbance_count            INTEGER,
    sleep_performance_percentage REAL,
    sleep_efficiency_percentage  REAL,
    respiratory_rate             REAL,
    synced_at                    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source, external_id)
);

CREATE TABLE IF NOT EXISTS activities (
    id               SERIAL      PRIMARY KEY,
    user_id          INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source           TEXT        NOT NULL,
    external_id      TEXT        NOT NULL,
    date             DATE        NOT NULL,
    sport_name       TEXT,
    sport_id         INTEGER,
    activity_category TEXT,                -- 'cardio' | 'strength' | 'flexibility' | 'sport' | 'other'
    score_state      TEXT,
    start_time       TIMESTAMPTZ,
    end_time         TIMESTAMPTZ,
    duration_seconds INTEGER,
    distance_meters  REAL,
    strain           REAL,
    energy_kcal      REAL,
    avg_heart_rate   INTEGER,
    max_heart_rate   INTEGER,
    zone_zero_milli  BIGINT,
    zone_one_milli   BIGINT,
    zone_two_milli   BIGINT,
    zone_three_milli BIGINT,
    zone_four_milli  BIGINT,
    zone_five_milli  BIGINT,
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source, external_id)
);

-- Add activity_category to existing installs that were already migrated
ALTER TABLE activities ADD COLUMN IF NOT EXISTS activity_category TEXT;


-- -----------------------------------------------------------------------------
-- Migrate: rename cardio_workouts → activities (idempotent)
-- -----------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (SELECT FROM pg_tables WHERE tablename = 'cardio_workouts' AND schemaname = 'public')
    AND NOT EXISTS (SELECT FROM pg_tables WHERE tablename = 'activities' AND schemaname = 'public')
    THEN
        ALTER TABLE cardio_workouts RENAME TO activities;
        ALTER INDEX IF EXISTS idx_cardio_workouts_user_date RENAME TO idx_activities_user_date;
        ALTER INDEX IF EXISTS idx_cardio_workouts_sport RENAME TO idx_activities_sport;
    END IF;
END $$;


-- -----------------------------------------------------------------------------
-- Body composition — source-agnostic
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS body_measurements (
    id                SERIAL      PRIMARY KEY,
    user_id           INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    external_id       TEXT        NOT NULL,
    measured_at       TIMESTAMPTZ NOT NULL,
    date              DATE        NOT NULL,
    source            TEXT        NOT NULL,
    weight_kg         REAL,
    fat_free_mass_kg  REAL,
    fat_ratio         REAL,
    fat_mass_kg       REAL,
    muscle_mass_kg    REAL,
    hydration_kg      REAL,
    bone_mass_kg      REAL,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, source, external_id)
);


-- -----------------------------------------------------------------------------
-- Nutrition — Cronometer (or any future source)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS nutrition_daily (
    id                     SERIAL      PRIMARY KEY,
    user_id                INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date                   DATE        NOT NULL,
    source                 TEXT        NOT NULL DEFAULT 'cronometer',
    energy_kcal            REAL,
    alcohol_g              REAL,
    caffeine_mg            REAL,
    oxalate_mg             REAL,
    phytate_mg             REAL,
    water_g                REAL,
    b1_thiamine_mg         REAL,
    b2_riboflavin_mg       REAL,
    b3_niacin_mg           REAL,
    b5_pantothenic_acid_mg REAL,
    b6_pyridoxine_mg       REAL,
    b12_cobalamin_ug       REAL,
    folate_ug              REAL,
    vitamin_a_ug           REAL,
    vitamin_c_mg           REAL,
    vitamin_d_iu           REAL,
    vitamin_e_mg           REAL,
    vitamin_k_ug           REAL,
    calcium_mg             REAL,
    copper_mg              REAL,
    iron_mg                REAL,
    magnesium_mg           REAL,
    manganese_mg           REAL,
    phosphorus_mg          REAL,
    potassium_mg           REAL,
    selenium_ug            REAL,
    sodium_mg              REAL,
    zinc_mg                REAL,
    net_carbs_g            REAL,
    carbs_g                REAL,
    fiber_g                REAL,
    insoluble_fiber_g      REAL,
    soluble_fiber_g        REAL,
    starch_g               REAL,
    sugars_g               REAL,
    added_sugars_g         REAL,
    fat_g                  REAL,
    cholesterol_mg         REAL,
    monounsaturated_g      REAL,
    polyunsaturated_g      REAL,
    saturated_g            REAL,
    trans_fats_g           REAL,
    omega3_g               REAL,
    ala_g                  REAL,
    dha_g                  REAL,
    epa_g                  REAL,
    omega6_g               REAL,
    aa_g                   REAL,
    la_g                   REAL,
    cystine_g              REAL,
    histidine_g            REAL,
    isoleucine_g           REAL,
    leucine_g              REAL,
    lysine_g               REAL,
    methionine_g           REAL,
    phenylalanine_g        REAL,
    protein_g              REAL,
    threonine_g            REAL,
    tryptophan_g           REAL,
    tyrosine_g             REAL,
    valine_g               REAL,
    completed              BOOLEAN,
    synced_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, date)
);


-- -----------------------------------------------------------------------------
-- Nutrition — Cronometer Servings / food-item level (CSV export)
-- Each row is one food item logged in a meal; no UNIQUE constraint because
-- the same food can appear multiple times in a day. Idempotency is handled
-- by DELETE-then-INSERT on the affected date range at sync time.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nutrition_foods (
    id                     SERIAL      PRIMARY KEY,
    user_id                INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    -- date of the log entry; joined to nutrition_daily and workouts on this column
    date                   DATE        NOT NULL,
    -- time-of-day the item was logged (NULL when not present in export)
    logged_at              TIME,
    meal_group             TEXT,       -- e.g. 'Breakfast', 'Lunch', 'Dinner', 'Snack'
    food_name              TEXT        NOT NULL,
    amount                 TEXT,       -- raw string from CSV, e.g. "1 cup"
    category               TEXT,
    energy_kcal            REAL, alcohol_g REAL, caffeine_mg REAL, oxalate_mg REAL,
    phytate_mg REAL, water_g REAL, b1_thiamine_mg REAL, b2_riboflavin_mg REAL,
    b3_niacin_mg REAL, b5_pantothenic_acid_mg REAL, b6_pyridoxine_mg REAL,
    b12_cobalamin_ug REAL, folate_ug REAL, vitamin_a_ug REAL, vitamin_c_mg REAL,
    vitamin_d_iu REAL, vitamin_e_mg REAL, vitamin_k_ug REAL, calcium_mg REAL,
    copper_mg REAL, iron_mg REAL, magnesium_mg REAL, manganese_mg REAL,
    phosphorus_mg REAL, potassium_mg REAL, selenium_ug REAL, sodium_mg REAL,
    zinc_mg REAL, net_carbs_g REAL, carbs_g REAL, fiber_g REAL,
    insoluble_fiber_g REAL, soluble_fiber_g REAL, starch_g REAL, sugars_g REAL,
    added_sugars_g REAL, fat_g REAL, cholesterol_mg REAL, monounsaturated_g REAL,
    polyunsaturated_g REAL, saturated_g REAL, trans_fats_g REAL, omega3_g REAL,
    omega6_g REAL, ala_g REAL, dha_g REAL, epa_g REAL, aa_g REAL, la_g REAL,
    cystine_g REAL, histidine_g REAL, isoleucine_g REAL, leucine_g REAL,
    lysine_g REAL, methionine_g REAL, phenylalanine_g REAL, protein_g REAL,
    threonine_g REAL, tryptophan_g REAL, tyrosine_g REAL, valine_g REAL
);
CREATE INDEX IF NOT EXISTS idx_nutrition_foods_user_date ON nutrition_foods (user_id, date);


-- -----------------------------------------------------------------------------
-- Strength — Strong app (CSV export)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS strong_workouts (
    id               SERIAL      PRIMARY KEY,
    user_id          INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    external_id      TEXT        NOT NULL,
    title            TEXT,
    started_at       TIMESTAMPTZ,
    duration_seconds INTEGER,
    synced_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, external_id)
);

CREATE TABLE IF NOT EXISTS strong_exercises (
    id             SERIAL  PRIMARY KEY,
    workout_id     INTEGER NOT NULL REFERENCES strong_workouts(id) ON DELETE CASCADE,
    title          TEXT    NOT NULL,
    notes          TEXT,
    exercise_index INTEGER
);

CREATE TABLE IF NOT EXISTS strong_sets (
    id               SERIAL  PRIMARY KEY,
    exercise_id      INTEGER NOT NULL REFERENCES strong_exercises(id) ON DELETE CASCADE,
    set_index        INTEGER,
    weight_kg        REAL,
    reps             INTEGER,
    duration_seconds INTEGER,
    distance_meters  REAL,
    rpe              REAL,
    estimated_1rm    REAL,
    performance_tag  TEXT
);

CREATE INDEX IF NOT EXISTS idx_strong_workouts_user ON strong_workouts (user_id, started_at);


-- -----------------------------------------------------------------------------
-- Agent — sessions, messages, insights
-- -----------------------------------------------------------------------------

-- A conversation session. Title is either auto-generated from the first message
-- or set by the user.
CREATE TABLE IF NOT EXISTS sessions (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT,
    summary    TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS summary TEXT;

-- Full message history for a session. Tool calls are stored as role='tool'
-- with tool_name populated. This is the source of truth fed back into the
-- LangChain agent as chat_history on resume.
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL      PRIMARY KEY,
    session_id INTEGER     NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL,  -- 'human' | 'ai' | 'tool'
    content    TEXT        NOT NULL,
    tool_name  TEXT,                  -- populated when role = 'tool'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS insights (
    id               SERIAL      PRIMARY KEY,
    user_id          INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id       INTEGER     REFERENCES sessions(id) ON DELETE SET NULL,
    correlative_tool TEXT        NOT NULL,
    insight          TEXT        NOT NULL,
    effect           TEXT        NOT NULL CHECK (effect IN ('positive','negative','neutral')),
    confidence       TEXT        NOT NULL CHECK (confidence IN ('strong','moderate')),
    date_derived     DATE        NOT NULL,
    status           TEXT        NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active','superseded','dismissed')),
    superseded_by    INTEGER     REFERENCES insights(id) ON DELETE SET NULL,
    pinned           BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


CREATE TABLE IF NOT EXISTS goals (
    id           SERIAL      PRIMARY KEY,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id   INTEGER     REFERENCES sessions(id) ON DELETE SET NULL,
    raw_input    TEXT        NOT NULL,
    goal_text    TEXT        NOT NULL,
    domains      JSONB       NOT NULL DEFAULT '[]',
    target_date  DATE,
    status       TEXT        NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active','achieved','abandoned')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS protocols (
    id            SERIAL      PRIMARY KEY,
    user_id       INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id    INTEGER     REFERENCES sessions(id) ON DELETE SET NULL,
    goal_id       INTEGER     NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    insight_ids   JSONB       NOT NULL DEFAULT '[]',
    protocol_text TEXT        NOT NULL,
    start_date    DATE        NOT NULL,
    review_date   DATE        NOT NULL,
    status        TEXT        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active','completed','abandoned')),
    outcome       TEXT        CHECK (outcome IN ('effective','ineffective','inconclusive')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS actions (
    id           SERIAL      PRIMARY KEY,
    protocol_id  INTEGER     REFERENCES protocols(id) ON DELETE CASCADE,
    goal_id      INTEGER     REFERENCES goals(id) ON DELETE CASCADE,
    user_id      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_text  TEXT        NOT NULL,
    metric       TEXT        NOT NULL,
    condition    TEXT        NOT NULL CHECK (condition IN ('less_than','greater_than','equals')),
    target_value NUMERIC     NOT NULL,
    data_source  TEXT        NOT NULL,
    frequency    TEXT        NOT NULL DEFAULT 'daily'
                             CHECK (frequency IN ('daily','weekly')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT actions_check_parent CHECK (
        (protocol_id IS NOT NULL AND goal_id IS NULL) OR
        (protocol_id IS NULL AND goal_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS action_compliance (
    id              SERIAL      PRIMARY KEY,
    action_id       INTEGER     NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
    user_id         INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start_date DATE        NOT NULL,
    target_value    NUMERIC     NOT NULL,
    actual_value    NUMERIC,          -- NULL means data was unavailable
    met             BOOLEAN,          -- NULL means data was unavailable
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (action_id, week_start_date)
);


-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------

-- Health data — all queries are per-user and date-ranged
CREATE INDEX IF NOT EXISTS idx_hevy_workouts_user_start    ON hevy_workouts      (user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_recovery_user_date          ON recovery           (user_id, date);
CREATE INDEX IF NOT EXISTS idx_sleep_user_date             ON sleep              (user_id, date);
CREATE INDEX IF NOT EXISTS idx_body_measurements_user_date ON body_measurements  (user_id, date);
CREATE INDEX IF NOT EXISTS idx_nutrition_daily_user_date   ON nutrition_daily    (user_id, date);
CREATE INDEX IF NOT EXISTS idx_activities_user_date ON activities (user_id, date);
CREATE INDEX IF NOT EXISTS idx_activities_sport     ON activities (user_id, sport_name);
CREATE INDEX IF NOT EXISTS idx_data_imports_user           ON user_data_imports  (user_id, data_type);

-- Agent — session lookup and message retrieval are the hot paths
CREATE INDEX IF NOT EXISTS idx_sessions_user_id           ON sessions  (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_id        ON messages  (session_id);
CREATE INDEX IF NOT EXISTS idx_insights_user_status       ON insights  (user_id, status);
CREATE INDEX IF NOT EXISTS idx_insights_correlative       ON insights  (user_id, correlative_tool, status);
CREATE INDEX IF NOT EXISTS idx_goals_user_status          ON goals     (user_id, status);
CREATE INDEX IF NOT EXISTS idx_protocols_user_status      ON protocols (user_id, status);
CREATE INDEX IF NOT EXISTS idx_protocols_goal_id          ON protocols (goal_id);
CREATE INDEX IF NOT EXISTS idx_actions_protocol_id        ON actions   (protocol_id);
CREATE INDEX IF NOT EXISTS idx_compliance_action_week     ON action_compliance (action_id, week_start_date);

-- One active protocol per goal (DB-level guard)
CREATE UNIQUE INDEX IF NOT EXISTS idx_protocols_one_active_per_goal
    ON protocols (goal_id) WHERE (status = 'active');

-- Bloodwork / lab results (values encrypted at rest)
CREATE TABLE IF NOT EXISTS biomarkers (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    test_date       DATE NOT NULL,
    marker_name     TEXT NOT NULL,
    value           TEXT NOT NULL,
    unit            TEXT,
    reference_low   TEXT,
    reference_high  TEXT,
    status          TEXT,
    source          TEXT NOT NULL DEFAULT 'pdf_upload'
                        CHECK (source IN ('pdf_upload', 'photo', 'manual')),
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, test_date, marker_name)
);
CREATE INDEX IF NOT EXISTS idx_biomarkers_user_date ON biomarkers (user_id, test_date);

-- Migrate: allow direct goal→action (no protocol required)
ALTER TABLE actions ADD COLUMN IF NOT EXISTS goal_id INTEGER REFERENCES goals(id) ON DELETE CASCADE;
ALTER TABLE actions ALTER COLUMN protocol_id DROP NOT NULL;
ALTER TABLE actions DROP CONSTRAINT IF EXISTS actions_check_parent;
ALTER TABLE actions ADD CONSTRAINT actions_check_parent CHECK (
    (protocol_id IS NOT NULL AND goal_id IS NULL) OR
    (protocol_id IS NULL AND goal_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_actions_goal_id ON actions (goal_id);

-- Migrate: add human-readable title to protocols
ALTER TABLE protocols ADD COLUMN IF NOT EXISTS title TEXT;

-- Migrate: add short title to goals and insights
ALTER TABLE goals    ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE insights ADD COLUMN IF NOT EXISTS title TEXT;

-- Migrate: track action modifications
ALTER TABLE actions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();


-- -----------------------------------------------------------------------------
-- Views  (scoped to user_id — app layer always filters by user_id)
-- -----------------------------------------------------------------------------

CREATE OR REPLACE VIEW v_exercise_prs AS
WITH working_sets AS (
    SELECT
        s.estimated_1rm,
        s.weight_kg,
        s.reps,
        e.exercise_template_id,
        e.title        AS exercise_title,
        w.user_id,
        w.hevy_id      AS workout_hevy_id,
        w.title        AS workout_title,
        w.start_time
    FROM hevy_sets s
    JOIN hevy_exercises e ON s.exercise_id  = e.id
    JOIN hevy_workouts  w ON e.workout_id   = w.id
    WHERE s.estimated_1rm IS NOT NULL
      AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY user_id, exercise_template_id
            ORDER BY estimated_1rm DESC, weight_kg DESC, start_time ASC
        ) AS rn
    FROM working_sets
)
SELECT
    user_id,
    exercise_template_id,
    exercise_title,
    estimated_1rm  AS pr_1rm_kg,
    weight_kg      AS pr_weight_kg,
    reps           AS pr_reps,
    workout_hevy_id,
    workout_title,
    start_time     AS pr_date
FROM ranked
WHERE rn = 1
ORDER BY pr_1rm_kg DESC;


CREATE OR REPLACE VIEW v_workout_1rm AS
WITH working_sets AS (
    SELECT
        s.estimated_1rm,
        s.weight_kg,
        s.reps,
        s.set_index,
        e.exercise_template_id,
        e.title       AS exercise_title,
        w.id          AS workout_id,
        w.user_id,
        w.hevy_id     AS workout_hevy_id,
        w.title       AS workout_title,
        w.start_time
    FROM hevy_sets s
    JOIN hevy_exercises e ON s.exercise_id = e.id
    JOIN hevy_workouts  w ON e.workout_id  = w.id
    WHERE s.estimated_1rm IS NOT NULL
      AND (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
),
ranked AS (
    SELECT *,
        ROW_NUMBER() OVER (
            PARTITION BY workout_id, exercise_template_id
            ORDER BY estimated_1rm DESC, weight_kg DESC, set_index ASC
        ) AS rn
    FROM working_sets
)
SELECT
    user_id,
    workout_hevy_id,
    workout_title,
    start_time            AS workout_date,
    exercise_template_id,
    exercise_title,
    estimated_1rm         AS session_best_1rm_kg,
    weight_kg             AS best_set_weight_kg,
    reps                  AS best_set_reps
FROM ranked
WHERE rn = 1
ORDER BY exercise_template_id, start_time;


CREATE OR REPLACE VIEW v_workout_performance AS
SELECT
    w.user_id,
    w.hevy_id                            AS workout_hevy_id,
    w.title                              AS workout_title,
    w.start_time::date                   AS workout_date,
    w.start_time,
    COUNT(s.id)                          AS total_sets,
    SUM(CASE WHEN s.performance_tag = 'PR'      THEN 1 ELSE 0 END) AS pr_sets,
    SUM(CASE WHEN s.performance_tag = 'Better'  THEN 1 ELSE 0 END) AS better_sets,
    SUM(CASE WHEN s.performance_tag = 'Neutral' THEN 1 ELSE 0 END) AS neutral_sets,
    SUM(CASE WHEN s.performance_tag = 'Worse'   THEN 1 ELSE 0 END) AS worse_sets,
    ROUND(AVG(CASE
        WHEN s.performance_tag = 'PR'      THEN 3.0
        WHEN s.performance_tag = 'Better'  THEN 2.0
        WHEN s.performance_tag = 'Neutral' THEN 1.0
        WHEN s.performance_tag = 'Worse'   THEN 0.0
    END)::numeric, 2)                    AS performance_score,
    CASE
        WHEN MAX(CASE WHEN s.performance_tag = 'PR'     THEN 3 ELSE 0 END) = 3 THEN 'PR'
        WHEN MAX(CASE WHEN s.performance_tag = 'Better' THEN 2 ELSE 0 END) = 2 THEN 'Better'
        WHEN MAX(CASE WHEN s.performance_tag = 'Worse'  THEN 1 ELSE 0 END) = 1 THEN 'Neutral'
        ELSE 'Worse'
    END                                  AS best_tag
FROM hevy_workouts w
JOIN hevy_exercises e ON e.workout_id  = w.id
JOIN hevy_sets      s ON s.exercise_id = e.id
WHERE (s.set_type IS NULL OR s.set_type NOT IN ('warmup', 'dropset'))
GROUP BY w.id
ORDER BY w.start_time DESC;
