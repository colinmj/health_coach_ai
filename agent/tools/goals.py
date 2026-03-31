import datetime
import json
import re

from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

import analytics.goals as goals_analytics
import analytics.compliance as compliance_analytics
from db.schema import get_connection, get_request_user_id
from agent.tools._config import _DOMAIN_ALLOWLIST, _CONFIDENCE_RANK, DEFAULT_SOURCES


@tool
def create_goal(
    goal_text: str,
    domains: str,
    title: str = "",
    target_date: str = "",
) -> str:
    """Save a confirmed health goal and generate a protocol with measurable actions.

    Call this ONLY after the goal has been refined and confirmed by the user in conversation.
    goal_text: the final, specific, measurable goal statement.
    domains: JSON array of relevant domains, e.g. '["body_composition","nutrition"]'.
             Valid values: strength, recovery, body_composition, nutrition.
    title: a short 4-7 word title for the goal (e.g. 'Build deadlift to 200kg').
    target_date: optional YYYY-MM-DD deadline string.

    Generates a protocol and 2-3 measurable actions using its own focused prompt.
    Enforces a cap of 3 active goals.
    Returns a JSON summary of the created goal, protocol, and actions.
    """
    user_id = get_request_user_id()

    llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0, timeout=60, stop=None).with_retry(
        retry_if_exception_type=(AnthropicOverloadedError,),
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )
    today = datetime.date.today().isoformat()

    try:
        parsed_domains = [d for d in json.loads(domains) if d in _DOMAIN_ALLOWLIST]
    except (json.JSONDecodeError, TypeError):
        parsed_domains = []

    target_date_val = target_date.strip() or None
    title_val = title.strip() or None

    # Generate protocol + actions with a focused, self-contained system prompt
    active_insights = goals_analytics.get_active_insights(user_id)
    insights_text = json.dumps(active_insights) if active_insights else "None"
    active_sources = list(DEFAULT_SOURCES.keys())

    protocol_resp = llm.invoke([
        SystemMessage(content=(
            "You are a health protocol designer. Given a confirmed health goal, decide whether "
            "it is 'simple' or 'complex', then generate the appropriate structure.\n\n"
            f"Today: {today}. Active data sources: {active_sources}.\n\n"
            "Use 'simple' when the goal maps to a single measurable metric with a clear numeric "
            "target and no multi-step strategy is needed "
            "(e.g. 'eat 30g fiber/day', 'drink 2L water/day', 'sleep 8h/night').\n"
            "Use 'complex' when multiple interdependent actions are needed or the goal benefits "
            "from a rationale or adaptive strategy "
            "(e.g. 'increase bench press 1RM', 'lose 5kg body fat').\n\n"
            "Rules for actions:\n"
            "- Each action must be measurable against one of the active data sources.\n"
            "- metric must be one of: calories, protein_g, carbs_g, fat_g, fiber_g, "
            "workout_frequency, activity_frequency, running_frequency.\n"
            "- Simple goals: 1 action. Complex goals: 2-3 actions.\n"
            "- If insights exist, incorporate them into complex protocol rationale.\n"
            "- For complex goals, review_date should be 4 weeks from today.\n\n"
            "Return only raw JSON. No markdown, no code fences, no commentary — just the JSON object.\n"
            "Simple: "
            '{"type": "simple", "actions": [{"action_text": "...", "metric": "...", '
            '"condition": "less_than|greater_than|equals", '
            '"target_value": <number>, "data_source": "...", "frequency": "daily|weekly"}]}\n'
            "Complex: "
            '{"type": "complex", "title": "3-6 word protocol name", "protocol_text": "...", "review_date": "YYYY-MM-DD", '
            '"actions": [{"action_text": "...", "metric": "...", '
            '"condition": "less_than|greater_than|equals", '
            '"target_value": <number>, "data_source": "...", "frequency": "daily|weekly"}]}'
        )),
        HumanMessage(content=f"Goal: {goal_text}\nActive insights: {insights_text}"),
    ])
    try:
        content = str(protocol_resp.content)
        # Extract JSON from markdown code fences if present; take the last block
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
        if blocks:
            content = blocks[-1].strip()
        protocol_data = json.loads(content)
    except json.JSONDecodeError:
        return f"Failed to parse response. LLM returned: {protocol_resp.content}"

    goal_type = protocol_data.get("type", "complex")

    # Validate actions
    valid_metrics = {
        "calories", "protein_g", "carbs_g", "fat_g", "fiber_g",
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
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM goals WHERE user_id = %s AND status = 'active'",
            (user_id,),
        ).fetchone()
        if row is None:
            return "Failed to check active goal count. Please try again."
        active_count = row["n"]
        if active_count >= 3:
            return "You already have 3 active goals. Mark one as achieved or abandoned before adding a new one."

        # Insert goal
        goal_row = conn.execute(
            "INSERT INTO goals (user_id, raw_input, goal_text, title, domains, target_date) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
            (user_id, goal_text, goal_text, title_val, json.dumps(parsed_domains), target_date_val),
        ).fetchone()
        if goal_row is None:
            return "Failed to create goal. Please try again."
        goal_id = goal_row["id"]

        if goal_type == "simple":
            # Direct actions — no protocol needed
            inserted_actions = []
            for a in actions:
                conn.execute(
                    "INSERT INTO actions (goal_id, user_id, action_text, metric, condition, target_value, data_source, frequency) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (goal_id, user_id, a["action_text"], a["metric"], a["condition"],
                     a["target_value"], a["data_source"], a.get("frequency", "daily")),
                )
                inserted_actions.append(a)

            return json.dumps({
                "goal_id": goal_id,
                "goal_text": goal_text,
                "domains": parsed_domains,
                "target_date": target_date_val,
                "actions": inserted_actions,
            })

        else:
            # Complex goal — insert protocol then actions
            protocol_title = protocol_data.get("title", "")
            protocol_row = conn.execute(
                "INSERT INTO protocols (user_id, goal_id, insight_ids, title, protocol_text, start_date, review_date) "
                "VALUES (%s, %s, '[]'::jsonb, %s, %s, %s, %s) RETURNING id",
                (user_id, goal_id, protocol_title, protocol_data["protocol_text"], today, protocol_data["review_date"]),
            ).fetchone()
            if protocol_row is None:
                return "Failed to create protocol. Please try again."
            protocol_id = protocol_row["id"]

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
                "protocol_id": protocol_id,
                "protocol_title": protocol_title,
                "review_date": protocol_data["review_date"],
                "actions": inserted_actions,
            })


@tool
def get_goals() -> str:
    """Return all goals with their protocols and actions.
    Returns a JSON list of goals, each with nested protocols and actions."""
    user_id = get_request_user_id()
    return json.dumps(goals_analytics.get_goals_with_protocols_and_actions(user_id))


@tool
def save_insight(
    correlative_tool: str,
    insight: str,
    effect: str,
    confidence: str,
    title: str = "",
    session_id: str = "",
) -> str:
    """Save a data-derived insight about a health correlation.
    correlative_tool: the tool name that produced the data (e.g. 'get_sleep_vs_performance').
    insight: the insight text.
    effect: 'positive', 'negative', or 'neutral'.
    confidence: 'strong' or 'moderate'.
    title: a short 5-8 word title summarising the insight (e.g. 'Sleep boosts next-day strength').
    A stronger insight for the same tool supersedes a weaker one.
    Enforces caps: 7 active total, 3 pinned."""
    user_id = get_request_user_id()

    if effect not in ("positive", "negative", "neutral"):
        return f"Invalid effect '{effect}'. Must be positive, negative, or neutral."
    if confidence not in ("strong", "moderate"):
        return f"Invalid confidence '{confidence}'. Must be strong or moderate."

    today = datetime.date.today().isoformat()
    sid = int(session_id) if session_id.strip() else None
    title_val = title.strip() or None

    with get_connection() as conn:
        counts = conn.execute(
            "SELECT COUNT(*) FILTER (WHERE status = 'active') AS total, "
            "COUNT(*) FILTER (WHERE status = 'active' AND pinned) AS pinned "
            "FROM insights WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        if counts is None:
            return "Failed to check insight count. Please try again."

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
            if counts["total"] - 1 >= 7:
                return "Active insight cap (7) reached. Dismiss an insight before saving a new one."

            new_row = conn.execute(
                "INSERT INTO insights (user_id, session_id, correlative_tool, title, insight, effect, confidence, date_derived) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, sid, correlative_tool, title_val, insight, effect, confidence, today),
            ).fetchone()
            if new_row is None:
                return "Failed to save insight. Please try again."
            new_id = new_row["id"]
            conn.execute(
                "UPDATE insights SET status = 'superseded', superseded_by = %s, updated_at = NOW() WHERE id = %s",
                (new_id, existing["id"]),
            )
            return json.dumps({"saved": True, "insight_id": new_id, "superseded": existing["id"]})

        else:
            if counts["total"] >= 7:
                return "Active insight cap (7) reached. Dismiss an insight before saving a new one."

            new_row = conn.execute(
                "INSERT INTO insights (user_id, session_id, correlative_tool, title, insight, effect, confidence, date_derived) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (user_id, sid, correlative_tool, title_val, insight, effect, confidence, today),
            ).fetchone()
            if new_row is None:
                return "Failed to save insight. Please try again."
            new_id = new_row["id"]
            return json.dumps({"saved": True, "insight_id": new_id})


@tool
def get_insights() -> str:
    """Return all active insights, pinned first.
    Returns a JSON list of insight records."""
    user_id = get_request_user_id()
    return json.dumps(goals_analytics.get_active_insights(user_id))


@tool
def check_compliance(protocol_id: str = "") -> str:
    """Check weekly compliance for active protocols and their actions.
    Optionally pass a protocol_id to check only that protocol.
    Returns a JSON summary of actual vs target values for each action this week."""
    user_id = get_request_user_id()
    pid = int(protocol_id) if protocol_id.strip() else None
    return json.dumps(compliance_analytics.run_compliance_check(user_id, protocol_id=pid))


@tool
def update_goal_status(goal_id: str, status: str) -> str:
    """Update the status of a goal.
    goal_id: the goal's numeric ID.
    status: 'achieved' or 'abandoned'."""
    if status not in ("achieved", "abandoned"):
        return f"Invalid status '{status}'. Must be 'achieved' or 'abandoned'."
    user_id = get_request_user_id()
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
    user_id = get_request_user_id()
    with get_connection() as conn:
        result = conn.execute(
            "UPDATE protocols SET status = 'completed', outcome = %s, updated_at = NOW() "
            "WHERE id = %s AND user_id = %s RETURNING id",
            (outcome, int(protocol_id), user_id),
        ).fetchone()
    if not result:
        return f"Protocol {protocol_id} not found."
    return json.dumps({"updated": True, "protocol_id": int(protocol_id), "outcome": outcome})


@tool
def update_action(
    action_id: str,
    action_text: str = "",
    condition: str = "",
    target_value: str = "",
    frequency: str = "",
) -> str:
    """Update one or more fields on an existing action.

    action_id: the action's numeric ID (from get_goals output).
    action_text: new human-readable description. Leave blank to keep current.
    condition: 'less_than', 'greater_than', or 'equals'. Leave blank to keep current.
    target_value: new numeric target (e.g. '2600'). Leave blank to keep current.
    frequency: 'daily' or 'weekly'. Leave blank to keep current.

    metric and data_source cannot be changed — create a new action instead.
    At least one field must be provided.
    """
    if condition and condition not in ("less_than", "greater_than", "equals"):
        return f"Invalid condition '{condition}'. Must be 'less_than', 'greater_than', or 'equals'."
    if frequency and frequency not in ("daily", "weekly"):
        return f"Invalid frequency '{frequency}'. Must be 'daily' or 'weekly'."

    target_float: float | None = None
    if target_value.strip():
        try:
            target_float = float(target_value)
        except ValueError:
            return f"Invalid target_value '{target_value}'. Must be a number."

    # Whitelist of mutable fields — keys never come from user input (safe dynamic SQL)
    updates: dict[str, object] = {}
    if action_text.strip():
        updates["action_text"] = action_text.strip()
    if condition:
        updates["condition"] = condition
    if target_float is not None:
        updates["target_value"] = target_float
    if frequency:
        updates["frequency"] = frequency

    if not updates:
        return "No fields provided. Supply at least one of: action_text, condition, target_value, frequency."

    user_id = get_request_user_id()
    set_clause = ", ".join(f"{k} = %s" for k in updates) + ", updated_at = NOW()"
    values = list(updates.values()) + [int(action_id), user_id]

    with get_connection() as conn:
        result = conn.execute(
            f"UPDATE actions SET {set_clause} WHERE id = %s AND user_id = %s "  # noqa: S608
            "RETURNING id, action_text, condition, target_value, frequency",
            values,
        ).fetchone()

        if not result:
            return f"Action {action_id} not found."

        # Sync current week's compliance row when target_value changed
        if target_float is not None:
            today = datetime.date.today()
            week_start = today - datetime.timedelta(days=today.weekday())
            compliance_row = conn.execute(
                "SELECT actual_value FROM action_compliance "
                "WHERE action_id = %s AND week_start_date = %s AND user_id = %s",
                (int(action_id), week_start, user_id),
            ).fetchone()
            if compliance_row:
                actual = compliance_row["actual_value"]
                effective_condition = condition or result["condition"]
                if actual is not None:
                    if effective_condition == "less_than":
                        met = float(actual) < target_float
                    elif effective_condition == "greater_than":
                        met = float(actual) > target_float
                    else:
                        met = abs(float(actual) - target_float) < 0.001
                else:
                    met = None
                conn.execute(
                    "UPDATE action_compliance SET target_value = %s, met = %s "
                    "WHERE action_id = %s AND week_start_date = %s AND user_id = %s",
                    (target_float, met, int(action_id), week_start, user_id),
                )

    return json.dumps({
        "updated": True,
        "action_id": int(action_id),
        "action_text": result["action_text"],
        "condition": result["condition"],
        "target_value": float(result["target_value"]),
        "frequency": result["frequency"],
    })


@tool
def update_training_iq(level: str) -> str:
    """Update the user's Training IQ level when their questions, language, or demonstrated
    knowledge clearly suggests their understanding has meaningfully changed over multiple
    interactions. Use sparingly — only change the level when you have consistent evidence,
    not from a single question.
    level must be one of: beginner, novice, intermediate, advanced, elite."""
    valid = {"beginner", "novice", "intermediate", "advanced", "elite"}
    if level not in valid:
        return json.dumps({"error": f"Invalid level '{level}'. Must be one of: {', '.join(sorted(valid))}"})
    user_id = get_request_user_id()
    with get_connection() as conn:
        conn.execute("UPDATE users SET training_iq = %s WHERE id = %s", (level, user_id))
        conn.commit()
    return json.dumps({"updated": True, "training_iq": level})
