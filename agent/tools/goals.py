import datetime
import json
import re

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

    llm = ChatAnthropic(model_name="claude-sonnet-4-6", temperature=0, timeout=None, stop=None)
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
        assert row is not None
        active_count = row["n"]
        if active_count >= 3:
            return "You already have 3 active goals. Mark one as achieved or abandoned before adding a new one."

        # Insert goal
        goal_row = conn.execute(
            "INSERT INTO goals (user_id, raw_input, goal_text, title, domains, target_date) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
            (user_id, goal_text, goal_text, title_val, json.dumps(parsed_domains), target_date_val),
        ).fetchone()
        assert goal_row is not None
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
            assert protocol_row is not None
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
        assert counts is not None

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
            assert new_row is not None
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
            assert new_row is not None
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
