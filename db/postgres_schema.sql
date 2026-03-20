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
    id         SERIAL      PRIMARY KEY,
    email      TEXT        UNIQUE NOT NULL,
    name       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One row per (user, domain). Stores OAuth tokens and tracks which source is
-- active for each domain (strength, recovery, body_composition, nutrition).
CREATE TABLE IF NOT EXISTS user_integrations (
    id               SERIAL      PRIMARY KEY,
    user_id          INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    domain           TEXT        NOT NULL,  -- 'strength' | 'recovery' | 'body_composition' | 'nutrition'
    source           TEXT        NOT NULL,  -- 'hevy' | 'whoop' | 'withings' | 'cronometer'
    is_active        BOOLEAN     NOT NULL DEFAULT TRUE,
    access_token     TEXT,
    refresh_token    TEXT,
    token_expires_at TIMESTAMPTZ,
    last_synced_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, domain)
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
-- Recovery — Whoop (or any future source)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS recovery (
    id                 SERIAL      PRIMARY KEY,
    user_id            INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    whoop_cycle_id     TEXT        NOT NULL,
    date               DATE        NOT NULL,
    source             TEXT        NOT NULL DEFAULT 'whoop',
    score_state        TEXT,
    recovery_score     REAL,
    hrv_rmssd_milli    REAL,
    resting_heart_rate REAL,
    spo2_percentage    REAL,
    skin_temp_celsius  REAL,
    synced_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, whoop_cycle_id)
);

CREATE TABLE IF NOT EXISTS sleep (
    id                           SERIAL      PRIMARY KEY,
    user_id                      INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    whoop_sleep_id               TEXT        NOT NULL,
    whoop_cycle_id               TEXT,
    date                         DATE        NOT NULL,
    source                       TEXT        NOT NULL DEFAULT 'whoop',
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
    UNIQUE (user_id, whoop_sleep_id)
);


-- -----------------------------------------------------------------------------
-- Body composition — Withings (or any future source)
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS body_measurements (
    id                SERIAL      PRIMARY KEY,
    user_id           INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    withings_group_id INTEGER     NOT NULL,
    measured_at       TIMESTAMPTZ NOT NULL,
    date              DATE        NOT NULL,
    source            TEXT        NOT NULL DEFAULT 'withings',
    weight_kg         REAL,
    fat_free_mass_kg  REAL,
    fat_ratio         REAL,
    fat_mass_kg       REAL,
    muscle_mass_kg    REAL,
    hydration_kg      REAL,
    bone_mass_kg      REAL,
    synced_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, withings_group_id)
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
-- Agent — sessions, messages, insights
-- -----------------------------------------------------------------------------

-- A conversation session. Title is either auto-generated from the first message
-- or set by the user.
CREATE TABLE IF NOT EXISTS sessions (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title      TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Full message history for a session. Tool calls are stored as role='tool'
-- with tool_name populated. This is the source of truth fed back into the
-- LangChain agent as chat_history on resume.
CREATE TABLE IF NOT EXISTS messages (
    id         SERIAL      PRIMARY KEY,
    session_id INTEGER     NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT        NOT NULL,  -- 'user' | 'assistant' | 'tool'
    content    TEXT        NOT NULL,
    tool_name  TEXT,                  -- populated when role = 'tool'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- User-curated insights saved from chat. At runtime, active insights are
-- fetched and injected into the agent's system prompt so the agent remembers
-- what the user has learned about themselves across sessions.
CREATE TABLE IF NOT EXISTS insights (
    id         SERIAL      PRIMARY KEY,
    user_id    INTEGER     NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id INTEGER     REFERENCES sessions(id) ON DELETE SET NULL,
    body       TEXT        NOT NULL,   -- e.g. "I sleep better when I eat more fiber"
    tags       TEXT[]      NOT NULL DEFAULT '{}',  -- e.g. '{sleep, nutrition}'
    is_active  BOOLEAN     NOT NULL DEFAULT TRUE,  -- soft delete / user can toggle off
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- -----------------------------------------------------------------------------
-- Indexes
-- -----------------------------------------------------------------------------

-- Health data — all queries are per-user and date-ranged
CREATE INDEX IF NOT EXISTS idx_hevy_workouts_user_start   ON hevy_workouts (user_id, start_time);
CREATE INDEX IF NOT EXISTS idx_recovery_user_date         ON recovery      (user_id, date);
CREATE INDEX IF NOT EXISTS idx_sleep_user_date            ON sleep         (user_id, date);
CREATE INDEX IF NOT EXISTS idx_body_measurements_user_date ON body_measurements (user_id, date);
CREATE INDEX IF NOT EXISTS idx_nutrition_daily_user_date  ON nutrition_daily   (user_id, date);

-- Agent — session lookup and message retrieval are the hot paths
CREATE INDEX IF NOT EXISTS idx_sessions_user_id           ON sessions  (user_id);
CREATE INDEX IF NOT EXISTS idx_messages_session_id        ON messages  (session_id);
CREATE INDEX IF NOT EXISTS idx_insights_user_active       ON insights  (user_id, is_active);


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
