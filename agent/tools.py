import datetime
import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

import analytics.hevy as hevy
import analytics.whoop as whoop
import analytics.withings as withings
import analytics.nutrition as nutrition
import analytics.correlations as corr
import analytics.goals as goals_analytics
import analytics.compliance as compliance_analytics
from db.schema import get_connection, get_local_user_id


# ---------------------------------------------------------------------------
# Strength tools  (domain: "strength")
# ---------------------------------------------------------------------------

@tool
def get_exercise_prs(exercise_template_id: str = "") -> str:
    """Return all-time best estimated 1RM per exercise.
    Optionally pass an exercise_template_id to filter to one exercise.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title,
    pr_1rm_kg, pr_weight_kg, pr_reps, workout_title, pr_date."""
    eid = exercise_template_id.strip() or None
    return json.dumps(hevy.get_exercise_prs(exercise_template_id=eid))


@tool
def get_workout_1rm_history(
    exercise_template_id: str = "",
    since: str = "",
    until: str = "",
) -> str:
    """Return best estimated 1RM per exercise per session over time.
    All args are optional. since/until are YYYY-MM-DD strings.
    Returns a JSON list of records with fields: workout_title, workout_date,
    exercise_template_id, exercise_title, session_best_1rm_kg, best_set_weight_kg, best_set_reps."""
    return json.dumps(hevy.get_workout_1rm_history(
        exercise_template_id=exercise_template_id.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_workout_performance(
    since: str = "",
    until: str = "",
    min_score: str = "",
) -> str:
    """Return workout-level performance summaries (PR/Better/Neutral/Worse set counts and score).
    All args are optional. since/until are YYYY-MM-DD strings. min_score is a float 0-3.
    Returns a JSON list of records with fields: workout_title, workout_date,
    total_sets, pr_sets, better_sets, neutral_sets, worse_sets, performance_score, best_tag."""
    return json.dumps(hevy.get_workout_performance(
        since=since.strip() or None,
        until=until.strip() or None,
        min_score=float(min_score) if min_score.strip() else None,
    ))


@tool
def get_exercise_list() -> str:
    """Return all known exercises with their template IDs and how many sessions they appear in.
    Use this to look up exercise_template_id values for other tools.
    Returns a JSON list of records with fields: exercise_template_id, exercise_title, session_count."""
    return json.dumps(hevy.get_exercise_template_ids())


# ---------------------------------------------------------------------------
# Recovery tools  (domain: "recovery")
# ---------------------------------------------------------------------------

@tool
def list_activity_sports(since: str = "", until: str = "") -> str:
    """Return the distinct sports the user has logged on Whoop, with session counts and averages.
    Use this first to discover available sport names before calling get_activities.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: sport_name, session_count, first_session, last_session,
    avg_strain, avg_energy_kcal."""
    return json.dumps(whoop.list_activity_sports(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_activities(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Return Whoop activity sessions, optionally filtered by sport name and date range.
    sport_name is matched case-insensitively — e.g. 'hockey' matches 'Ice Hockey'.
    Leave sport_name blank to get all activities across all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, sport_name, strain, avg_heart_rate, max_heart_rate,
    energy_kcal, zone_zero_milli through zone_five_milli."""
    return json.dumps(whoop.get_activities(
        sport_name=sport_name.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_recovery(since: str = "", until: str = "") -> str:
    """Return Whoop recovery scores and HRV data.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, recovery_score, hrv_rmssd_milli,
    resting_heart_rate, spo2_percentage, skin_temp_celsius, strain, daily_energy_kcal."""
    return json.dumps(whoop.get_recovery(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep(since: str = "", until: str = "", exclude_naps: bool = True) -> str:
    """Return Whoop sleep performance and architecture data.
    since/until are optional YYYY-MM-DD strings. exclude_naps defaults to True.
    Returns a JSON list of records with fields: date, sleep_performance_percentage,
    sleep_efficiency_percentage, total_rem_sleep_milli, total_slow_wave_sleep_milli,
    total_in_bed_time_milli, respiratory_rate."""
    return json.dumps(whoop.get_sleep(
        since=since.strip() or None,
        until=until.strip() or None,
        exclude_naps=exclude_naps,
    ))


# ---------------------------------------------------------------------------
# Body composition tools  (domain: "body_composition")
# ---------------------------------------------------------------------------

@tool
def get_body_composition(since: str = "", until: str = "") -> str:
    """Return Withings body composition measurements (weight, fat %, muscle mass, etc.).
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, weight_kg, fat_ratio,
    muscle_mass_kg, fat_free_mass_kg, bone_mass_kg."""
    return json.dumps(withings.get_body_composition(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


# ---------------------------------------------------------------------------
# Nutrition tools  (domain: "nutrition")
# ---------------------------------------------------------------------------

@tool
def get_nutrition(since: str = "", until: str = "") -> str:
    """Return daily macros and key performance micros from Cronometer.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list of records with fields: date, source, energy_kcal, protein_g,
    carbs_g, net_carbs_g, fat_g, fiber_g, sugars_g, magnesium_mg, sodium_mg,
    potassium_mg, vitamin_d_iu, iron_mg, calcium_mg, completed."""
    return json.dumps(nutrition.get_nutrition(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


# ---------------------------------------------------------------------------
# Correlation tools  (domain pairs — all domains they touch)
# ---------------------------------------------------------------------------

@tool
def get_hrv_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does HRV predict workout quality?' questions.
    Returns paired prior-night recovery data with each workout's performance score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, total_sets, prior_night_recovery_score, prior_night_hrv_milli, prior_night_rhr."""
    return json.dumps(corr.get_hrv_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does sleep quality affect training?' questions. Sleep durations are in minutes.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, prior_night_sleep_performance, prior_night_sleep_efficiency,
    prior_night_sws_minutes, prior_night_rem_minutes, prior_night_in_bed_minutes."""
    return json.dumps(corr.get_sleep_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_sleep_threshold_vs_performance(
    threshold_hours: str = "7",
    since: str = "",
    until: str = "",
) -> str:
    """Use for 'does sleeping more/less than X hours affect workout performance?' questions.
    Compares average performance score and PR rate for workouts preceded by nights above vs
    below the threshold. Returns two summary rows (above_threshold / below_threshold) with
    workout_count, avg_performance_score, avg_sleep_minutes, pr_workouts, better_workouts,
    worse_workouts. Default threshold is 7 hours."""
    return json.dumps(corr.get_sleep_threshold_vs_performance(
        threshold_hours=float(threshold_hours) if threshold_hours.strip() else 7.0,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_body_composition_vs_strength(
    since: str = "",
    until: str = "",
    days_window: str = "7",
) -> str:
    """Use for 'does body fat change track with strength?' questions.
    days_window controls how many days after a measurement to look for a workout.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: measurement_date, weight_kg, fat_ratio,
    muscle_mass_kg, fat_free_mass_kg, nearest_workout_date,
    avg_1rm_kg_across_exercises, exercises_tracked."""
    return json.dumps(corr.get_body_composition_vs_strength(
        since=since.strip() or None,
        until=until.strip() or None,
        days_window=int(days_window) if days_window.strip() else 7,
    ))


@tool
def get_nutrition_vs_performance(since: str = "", until: str = "") -> str:
    """Use for 'does nutrition affect workout quality?' questions (carbs, calories, etc.).
    Pairs same-day nutrition with each workout's performance score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, energy_kcal, protein_g, carbs_g, net_carbs_g, fat_g, fiber_g."""
    return json.dumps(corr.get_nutrition_vs_performance(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_protein_vs_strength(since: str = "", until: str = "") -> str:
    """Use for 'does protein intake correlate with strength over time?' questions.
    Pairs daily protein with average session 1RM on workout days.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, protein_g, energy_kcal,
    avg_session_1rm_kg, exercise_count."""
    return json.dumps(corr.get_protein_vs_strength(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_nutrition_vs_recovery(since: str = "", until: str = "") -> str:
    """Use for 'does what I eat affect my recovery?' questions.
    Pairs prior-day nutrition with next-day Whoop recovery score.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: recovery_date, recovery_score, hrv_rmssd_milli,
    prior_day_energy_kcal, prior_day_protein_g, prior_day_carbs_g, prior_day_fat_g."""
    return json.dumps(corr.get_nutrition_vs_recovery(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_carbs_prior_to_prs(since: str = "", until: str = "") -> str:
    """Use for 'did carb loading before PRs?' or 'carb intake before best workouts?' questions.
    For each PR workout, returns carb totals for each of the 3 prior days plus a 3-day average.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, pr_sets,
    carbs_day_minus_1, net_carbs_day_minus_1, carbs_day_minus_2, net_carbs_day_minus_2,
    carbs_day_minus_3, net_carbs_day_minus_3, avg_carbs_3d, avg_net_carbs_3d."""
    return json.dumps(corr.get_carbs_prior_to_prs(
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_nutrition_vs_activity(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Use for questions like 'how does carb/protein/fat intake the night before affect my
    performance in a specific sport?' (e.g. heart rate, strain, calories burned during hockey).
    Pairs prior-night nutrition with each activity session matching the sport.
    sport_name is matched case-insensitively. Leave blank to include all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: activity_date, sport_name, strain, avg_heart_rate,
    max_heart_rate, calories_burned, prior_night_energy_kcal, prior_night_carbs_g,
    prior_night_net_carbs_g, prior_night_protein_g, prior_night_fat_g, prior_night_sugars_g."""
    return json.dumps(corr.get_nutrition_vs_activity(
        sport_name=sport_name.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_activity_vs_strength(sport_name: str = "", since: str = "", until: str = "") -> str:
    """Use for 'does a prior-day sport/activity affect lifting performance?' questions
    (e.g. 'do my workouts suffer the day after running/powerlifting/kickboxing?').
    Pairs each Hevy strength session with any Whoop activity logged the day before.
    sport_name is matched case-insensitively — leave blank to include all sports.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: workout_date, workout_title, performance_score,
    best_tag, total_sets, prior_day_sport, prior_day_strain, prior_day_avg_hr,
    prior_day_max_hr, prior_day_calories."""
    return json.dumps(corr.get_activity_vs_strength(
        sport_name=sport_name.strip() or None,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_energy_balance_vs_weight(since: str = "", until: str = "") -> str:
    """Use for weight change goal questions: 'am I in a deficit?', 'why isn't my weight changing?',
    'is my calorie tracking accurate?', 'is Whoop overestimating my burn?'.
    Compares daily calories consumed (Cronometer) vs Whoop daily energy burn, then checks
    whether the resulting estimated surplus/deficit aligns with actual weight change.
    A large discrepancy between expected and actual weight change suggests a tracking error
    or inaccurate Whoop estimate.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, calories_consumed, calories_burned, daily_balance,
    rolling_7d_avg_consumed, rolling_7d_avg_burned, rolling_7d_avg_balance,
    rolling_7d_expected_weight_change_kg, weight_kg, weight_7d_ago_kg,
    actual_7d_weight_change_kg."""
    user_id = get_local_user_id()
    return json.dumps(corr.get_energy_balance_vs_weight(
        user_id=user_id,
        since=since.strip() or None,
        until=until.strip() or None,
    ))


@tool
def get_nutrition_vs_body_composition(
    since: str = "",
    until: str = "",
    days_window: str = "7",
) -> str:
    """Use for 'does calorie/macro intake correlate with body composition?' questions.
    days_window controls how many days around a nutrition entry to look for a body measurement.
    since/until are optional YYYY-MM-DD strings.
    Returns a JSON list with fields: date, energy_kcal, protein_g, carbs_g, fat_g,
    weight_kg, fat_ratio, muscle_mass_kg."""
    return json.dumps(corr.get_nutrition_vs_body_composition(
        since=since.strip() or None,
        until=until.strip() or None,
        days_window=int(days_window) if days_window.strip() else 7,
    ))


# ---------------------------------------------------------------------------
# Goals, insights, protocols, compliance tools  (no domain/source requirements)
# ---------------------------------------------------------------------------

_DOMAIN_ALLOWLIST = {"strength", "recovery", "body_composition", "nutrition"}
_CONFIDENCE_RANK = {"strong": 2, "moderate": 1}


@tool
def create_goal(raw_input: str) -> str:
    """Create a new health goal from natural language input.
    Parses the goal, generates a protocol with measurable actions, and saves everything.
    Returns a structured summary of the created goal, protocol, and actions.
    Enforces a cap of 3 active goals."""
    user_id = get_local_user_id()

    llm = ChatAnthropic(model="claude-sonnet-4-6", temperature=0)
    today = datetime.date.today().isoformat()

    # Call 1 — parse raw input
    parse_resp = llm.invoke([
        SystemMessage(content=(
            "Parse the user's health goal into JSON with exactly these keys: "
            '{"goal_text": "...", "domains": [...], "target_date": "YYYY-MM-DD or null"}. '
            f"Today is {today}. "
            "domains must only contain values from: strength, recovery, body_composition, nutrition. "
            "Return only valid JSON, no other text."
        )),
        HumanMessage(content=raw_input),
    ])
    try:
        parsed = json.loads(parse_resp.content)
    except json.JSONDecodeError:
        return f"Failed to parse goal. LLM returned: {parse_resp.content}"

    goal_text = parsed.get("goal_text", raw_input)
    domains = [d for d in parsed.get("domains", []) if d in _DOMAIN_ALLOWLIST]
    target_date = parsed.get("target_date") or None

    # Call 2 — generate protocol + actions
    active_insights = goals_analytics.get_active_insights(user_id)
    insights_text = json.dumps(active_insights) if active_insights else "None"
    active_sources = list(DEFAULT_SOURCES.keys())

    protocol_resp = llm.invoke([
        SystemMessage(content=(
            "Generate a protocol and 2-3 measurable actions for the given goal. "
            f"Active data sources: {active_sources}. "
            "Each action's data_source must be one of the active sources. "
            "Return only valid JSON with this structure: "
            '{"protocol_text": "...", "review_date": "YYYY-MM-DD", '
            '"actions": [{"action_text": "...", "metric": "...", "condition": "less_than|greater_than|equals", '
            '"target_value": <number>, "data_source": "...", "frequency": "daily|weekly"}]}. '
            "metric must be one of: calories, protein_g, carbs_g, fat_g, workout_frequency, "
            "activity_frequency, running_frequency. "
            "No other text, only JSON."
        )),
        HumanMessage(content=f"Goal: {goal_text}\nActive insights: {insights_text}"),
    ])
    try:
        protocol_data = json.loads(protocol_resp.content)
    except json.JSONDecodeError:
        return f"Failed to parse protocol. LLM returned: {protocol_resp.content}"

    # Validate actions
    valid_metrics = {
        "calories", "protein_g", "carbs_g", "fat_g",
        "workout_frequency", "activity_frequency", "running_frequency",
    }
    actions = [
        a for a in protocol_data.get("actions", [])
        if a.get("data_source") in active_sources
        and a.get("metric") in valid_metrics
    ]
    if not actions:
        return "Could not generate valid actions for the active data sources."

    with get_connection() as conn:
        # Enforce 3-active-goals cap
        active_count = conn.execute(
            "SELECT COUNT(*) AS n FROM goals WHERE user_id = %s AND status = 'active'",
            (user_id,),
        ).fetchone()["n"]
        if active_count >= 3:
            return "You already have 3 active goals. Mark one as achieved or abandoned before adding a new one."

        # Insert goal
        goal_id = conn.execute(
            "INSERT INTO goals (user_id, raw_input, goal_text, domains, target_date) "
            "VALUES (%s, %s, %s, %s::jsonb, %s) RETURNING id",
            (user_id, raw_input, goal_text, json.dumps(domains), target_date),
        ).fetchone()["id"]

        # Insert protocol
        protocol_id = conn.execute(
            "INSERT INTO protocols (user_id, goal_id, insight_ids, protocol_text, start_date, review_date) "
            "VALUES (%s, %s, '[]'::jsonb, %s, %s, %s) RETURNING id",
            (user_id, goal_id, protocol_data["protocol_text"], today, protocol_data["review_date"]),
        ).fetchone()["id"]

        # Insert actions
        inserted_actions = []
        for a in actions:
            conn.execute(
                "INSERT INTO actions (protocol_id, user_id, action_text, metric, condition, target_value, data_source, frequency) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (protocol_id, user_id, a["action_text"], a["metric"], a["condition"],
                 a["target_value"], a["data_source"], a.get("frequency", "daily")),
            )
            inserted_actions.append(a)

    return json.dumps({
        "goal_id": goal_id,
        "goal_text": goal_text,
        "domains": domains,
        "target_date": target_date,
        "protocol_id": protocol_id,
        "protocol_text": protocol_data["protocol_text"],
        "review_date": protocol_data["review_date"],
        "actions": inserted_actions,
    })


@tool
def get_goals() -> str:
    """Return all goals with their protocols and actions.
    Returns a JSON list of goals, each with nested protocols and actions."""
    user_id = get_local_user_id()
    return json.dumps(goals_analytics.get_goals_with_protocols_and_actions(user_id))


@tool
def save_insight(
    correlative_tool: str,
    insight: str,
    effect: str,
    confidence: str,
    session_id: str = "",
) -> str:
    """Save a data-derived insight about a health correlation.
    correlative_tool: the tool name that produced the data (e.g. 'get_sleep_vs_performance').
    insight: the insight text.
    effect: 'positive', 'negative', or 'neutral'.
    confidence: 'strong' or 'moderate'.
    A stronger insight for the same tool supersedes a weaker one.
    Enforces caps: 7 active total, 3 pinned."""
    user_id = get_local_user_id()

    if effect not in ("positive", "negative", "neutral"):
        return f"Invalid effect '{effect}'. Must be positive, negative, or neutral."
    if confidence not in ("strong", "moderate"):
        return f"Invalid confidence '{confidence}'. Must be strong or moderate."

    today = datetime.date.today().isoformat()
    sid = int(session_id) if session_id.strip() else None

    with get_connection() as conn:
        # Check caps
        counts = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE status = 'active') AS total, "
            "COUNT(*) FILTER (WHERE status = 'active' AND pinned) AS pinned "
            "FROM insights WHERE user_id = %s",
            (user_id,),
        ).fetchone()

        existing = conn.execute(
            "SELECT * FROM insights WHERE user_id = %s AND correlative_tool = %s AND status = 'active'",
            (user_id, correlative_tool),
        ).fetchone()

        if existing:
            new_rank = _CONFIDENCE_RANK[confidence]
            existing_rank = _CONFIDENCE_RANK[existing["confidence"]]
            if new_rank < existing_rank:
                return (
                    f"⚠️ A stronger insight already exists for {correlative_tool}. "
                    "Save anyway by calling save_insight with force=true."
                )
            # New is >= existing: check total cap (existing will be superseded, net +0)
            if counts["total"] - 1 >= 7:
                return "Active insight cap (7) reached. Dismiss an insight before saving a new one."

            new_id = conn.execute(
                "INSERT INTO insights (user_id, session_id, correlative_tool, insight, effect, confidence, date_derived) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, sid, correlative_tool, insight, effect, confidence, today),
            ).fetchone()["id"]
            conn.execute(
                "UPDATE insights SET status = 'superseded', superseded_by = %s, updated_at = NOW() WHERE id = %s",
                (new_id, existing["id"]),
            )
            return json.dumps({"saved": True, "insight_id": new_id, "superseded": existing["id"]})

        else:
            if counts["total"] >= 7:
                return "Active insight cap (7) reached. Dismiss an insight before saving a new one."

            new_id = conn.execute(
                "INSERT INTO insights (user_id, session_id, correlative_tool, insight, effect, confidence, date_derived) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, sid, correlative_tool, insight, effect, confidence, today),
            ).fetchone()["id"]
            return json.dumps({"saved": True, "insight_id": new_id})


@tool
def get_insights() -> str:
    """Return all active insights, pinned first.
    Returns a JSON list of insight records."""
    user_id = get_local_user_id()
    return json.dumps(goals_analytics.get_active_insights(user_id))


@tool
def check_compliance(protocol_id: str = "") -> str:
    """Check weekly compliance for active protocols and their actions.
    Optionally pass a protocol_id to check only that protocol.
    Returns a JSON summary of actual vs target values for each action this week."""
    user_id = get_local_user_id()
    pid = int(protocol_id) if protocol_id.strip() else None
    return json.dumps(compliance_analytics.run_compliance_check(user_id, protocol_id=pid))


@tool
def update_goal_status(goal_id: str, status: str) -> str:
    """Update the status of a goal.
    goal_id: the goal's numeric ID.
    status: 'achieved' or 'abandoned'."""
    if status not in ("achieved", "abandoned"):
        return f"Invalid status '{status}'. Must be 'achieved' or 'abandoned'."
    user_id = get_local_user_id()
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE goals SET status = %s, updated_at = NOW() WHERE id = %s AND user_id = %s RETURNING id",
            (status, int(goal_id), user_id),
        ).fetchone()
    if not result:
        return f"Goal {goal_id} not found."
    return json.dumps({"updated": True, "goal_id": int(goal_id), "status": status})


@tool
def assess_protocol(protocol_id: str, outcome: str) -> str:
    """Mark a protocol as completed with an outcome assessment.
    protocol_id: the protocol's numeric ID.
    outcome: 'effective', 'ineffective', or 'inconclusive'."""
    if outcome not in ("effective", "ineffective", "inconclusive"):
        return f"Invalid outcome '{outcome}'. Must be 'effective', 'ineffective', or 'inconclusive'."
    user_id = get_local_user_id()
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE protocols SET status = 'completed', outcome = %s, updated_at = NOW() "
            "WHERE id = %s AND user_id = %s RETURNING id",
            (outcome, int(protocol_id), user_id),
        ).fetchone()
    if not result:
        return f"Protocol {protocol_id} not found."
    return json.dumps({"updated": True, "protocol_id": int(protocol_id), "outcome": outcome})


# ---------------------------------------------------------------------------
# Registry — maps each tool to the domains and sources it requires.
#
# required_domains: the tool is excluded if any of these domains are not active.
# required_sources: the tool is excluded if the active source for a domain
#                   doesn't match. Omit a domain here to accept any source.
#
# Example: get_workout_performance requires strength=hevy because it relies on
# Hevy's performance tagging (PR/Better/Neutral/Worse). A Strong user with
# no equivalent tagging would not receive this tool.
# ---------------------------------------------------------------------------

TOOL_REGISTRY: list[tuple] = [
    # (tool_fn,                          required_domains,              required_sources)
    (get_exercise_prs,                   {"strength"},                  {"strength": "hevy"}),
    (get_workout_1rm_history,            {"strength"},                  {"strength": "hevy"}),
    (get_workout_performance,            {"strength"},                  {"strength": "hevy"}),
    (get_exercise_list,                  {"strength"},                  {"strength": "hevy"}),
    (list_activity_sports,               {"recovery"},                  {}),
    (get_activities,                     {"recovery"},                  {}),
    (get_recovery,                       {"recovery"},                  {}),
    (get_sleep,                          {"recovery"},                  {}),
    (get_body_composition,               {"body_composition"},          {}),
    (get_nutrition,                      {"nutrition"},                 {}),
    (get_hrv_vs_performance,             {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_vs_performance,           {"recovery", "strength"},      {"strength": "hevy"}),
    (get_sleep_threshold_vs_performance, {"recovery", "strength"},      {"strength": "hevy"}),
    (get_body_composition_vs_strength,   {"body_composition", "strength"}, {"strength": "hevy"}),
    (get_nutrition_vs_performance,       {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_protein_vs_strength,            {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_carbs_prior_to_prs,             {"nutrition", "strength"},     {"strength": "hevy"}),
    (get_nutrition_vs_recovery,          {"nutrition", "recovery"},     {}),
    (get_nutrition_vs_activity,          {"nutrition", "recovery"},     {}),
    (get_activity_vs_strength,           {"recovery", "strength"},      {"strength": "hevy"}),
    (get_nutrition_vs_body_composition,  {"nutrition", "body_composition"}, {}),
    (get_energy_balance_vs_weight,       {"nutrition", "recovery", "body_composition"}, {}),
    (create_goal,                        set(),                             {}),
    (get_goals,                          set(),                             {}),
    (save_insight,                       set(),                             {}),
    (get_insights,                       set(),                             {}),
    (check_compliance,                   set(),                             {}),
    (update_goal_status,                 set(),                             {}),
    (assess_protocol,                    set(),                             {}),
]

# Default source map for single-user local mode
DEFAULT_SOURCES: dict[str, str] = {
    "strength":         "hevy",
    "recovery":         "whoop",
    "body_composition": "withings",
    "nutrition":        "cronometer",
}


def build_tools(source_map: dict[str, str] = DEFAULT_SOURCES) -> list:
    """Return tools whose required domains and sources are satisfied by source_map.

    source_map maps domain → active source, e.g.:
        {"strength": "hevy", "recovery": "oura"}
    Tools requiring a domain not in source_map are excluded.
    Tools requiring a specific source for a domain are excluded if it doesn't match.
    """
    active_domains = set(source_map.keys())
    return [
        tool_fn
        for tool_fn, required_domains, required_sources in TOOL_REGISTRY
        if required_domains.issubset(active_domains)
        and all(source_map.get(domain) == source for domain, source in required_sources.items())
    ]


# Default: all tools (single-user local mode)
TOOLS = build_tools()
