import datetime
import json
import logging
import re

from anthropic._exceptions import OverloadedError as AnthropicOverloadedError
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

import analytics.goals as goals_analytics
import analytics.compliance as compliance_analytics
from db.schema import get_connection, get_request_user_id
from agent.tools._config import _DOMAIN_ALLOWLIST, _CONFIDENCE_RANK, DEFAULT_SOURCES, build_source_map

logger = logging.getLogger(__name__)


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
    Returns a plain-text summary of the created goal, protocol, and actions.
    """
    user_id = get_request_user_id()

    llm = ChatAnthropic(model_name="claude-haiku-4-5-20251001", temperature=0, timeout=30, max_tokens=500, stop=None).with_retry(
        retry_if_exception_type=(AnthropicOverloadedError,),
        stop_after_attempt=3,
        wait_exponential_jitter=True,
    )
    today = datetime.date.today().isoformat()

    try:
        parsed_domains = [d for d in json.loads(domains) if d in _DOMAIN_ALLOWLIST]
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("create_goal: could not parse domains %r — defaulting to []. Error: %s", domains, exc)
        parsed_domains = []

    target_date_val = target_date.strip() or None
    title_val = title.strip() or None

    # Generate protocol + actions with a focused, self-contained system prompt
    active_insights = goals_analytics.get_active_insights(user_id)
    insights_text = (
        json.dumps([{"title": i.get("title"), "effect": i.get("effect")} for i in active_insights])
        if active_insights else "None"
    )
    active_sources = list(build_source_map(user_id).keys())

    protocol_resp = llm.invoke([
        SystemMessage(content=(
            "You are a health action designer. Given a confirmed health goal, generate 1-3 measurable actions.\n\n"
            f"Today: {today}. Active data sources: {active_sources}.\n\n"
            "Rules for actions:\n"
            "- Each action must be measurable against one of the active data sources.\n"
            "- metric must be one of: calories, protein_g, carbs_g, fat_g, fiber_g, "
            "workout_frequency, activity_frequency, running_frequency.\n"
            "- Simple, single-metric goals need 1 action. Multi-faceted goals may have 2-3 actions.\n"
            "- If insights exist, use them to inform action targets.\n\n"
            "Return only raw JSON. No markdown, no code fences, no commentary — just the JSON object.\n"
            '{"actions": [{"action_text": "...", "metric": "...", '
            '"condition": "less_than|greater_than|equals", '
            '"target_value": <number>, "data_source": "...", "frequency": "daily|weekly"}]}'
        )),
        HumanMessage(content=f"Goal: {goal_text}\nActive insights: {insights_text}"),
    ])
    try:
        content = str(protocol_resp.content)
        blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
        if blocks:
            content = blocks[-1].strip()
        protocol_data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error(
            "create_goal: failed to parse protocol LLM response. goal_text=%r raw=%r error=%s",
            goal_text, protocol_resp.content, exc,
        )
        return f"Failed to parse protocol response. LLM returned: {protocol_resp.content}"

    # Validate actions
    valid_metrics = {
        "calories", "protein_g", "carbs_g", "fat_g", "fiber_g",
        "workout_frequency", "activity_frequency", "running_frequency",
    }
    raw_actions = protocol_data.get("actions", [])
    actions = [
        a for a in raw_actions
        if a.get("data_source") in active_sources
        and a.get("metric") in valid_metrics
    ]
    if not actions:
        logger.error(
            "create_goal: all actions filtered out. goal_text=%r active_sources=%r raw_actions=%r",
            goal_text, active_sources, raw_actions,
        )
        return "Could not generate valid actions for the active data sources."

    try:
        with get_connection() as conn:
            # Enforce 3-active-goals cap
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM goals WHERE user_id = %s AND status = 'active'",
                (user_id,),
            ).fetchone()
            if row is None:
                logger.error("create_goal: COUNT query returned None. user_id=%s", user_id)
                return "Failed to check active goal count. Please try again."
            active_count = row["n"]
            if active_count >= 3:
                return "You already have 3 active goals. Mark one as achieved or abandoned before adding a new one."

            # Enforce one active goal per domain
            if parsed_domains:
                domain_rows = conn.execute(
                    "SELECT goal_text, domains FROM goals WHERE user_id = %s AND status = 'active'",
                    (user_id,),
                ).fetchall()
                for existing in domain_rows:
                    existing_domains = existing["domains"] or []
                    overlap = set(parsed_domains) & set(existing_domains)
                    if overlap:
                        overlap_str = ", ".join(sorted(overlap))
                        return (
                            f"Domain conflict: you already have an active goal covering {overlap_str}. "
                            f"Only one active goal per domain is allowed. "
                            f"Existing goal: \"{existing['goal_text'][:80]}\". "
                            f"Mark it as achieved or abandoned before creating a new {overlap_str} goal."
                        )

            # Enforce one active action per metric
            proposed_metrics = [a["metric"] for a in actions]
            if proposed_metrics:
                conflict_rows = conn.execute(
                    """
                    SELECT DISTINCT a.metric FROM actions a
                    JOIN goals g ON g.id = a.goal_id
                    WHERE a.user_id = %s
                      AND a.metric = ANY(%s::text[])
                      AND g.status = 'active'
                    """,
                    (user_id, proposed_metrics),
                ).fetchall()
                if conflict_rows:
                    conflicts = ", ".join(r["metric"] for r in conflict_rows)
                    return (
                        f"Metric conflict: you already have active actions tracking {conflicts}. "
                        f"Only one active action per metric is allowed. "
                        f"Delete or complete the existing goal(s) covering {conflicts} before adding new ones."
                    )

            # Insert goal
            goal_row = conn.execute(
                "INSERT INTO goals (user_id, raw_input, goal_text, title, domains, target_date) "
                "VALUES (%s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
                (user_id, goal_text, goal_text, title_val, json.dumps(parsed_domains), target_date_val),
            ).fetchone()
            if goal_row is None:
                logger.error("create_goal: INSERT goals returned None. user_id=%s goal_text=%r", user_id, goal_text)
                return "Failed to create goal. Please try again."
            goal_id = goal_row["id"]

            # Insert actions directly under the goal
            inserted_actions = []
            for a in actions:
                conn.execute(
                    "INSERT INTO actions (goal_id, user_id, action_text, metric, condition, target_value, data_source, frequency) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (goal_id, user_id, a["action_text"], a["metric"], a["condition"],
                     a["target_value"], a["data_source"], a.get("frequency", "daily")),
                )
                inserted_actions.append(a)

            action_summaries = "; ".join(
                f"{a['action_text']} (target: {a['condition'].replace('_', ' ')} {a['target_value']} {a['metric']}, {a.get('frequency', 'daily')})"
                for a in inserted_actions
            )
            return (
                f"Goal saved (id={goal_id}): {goal_text}. "
                f"Actions: {action_summaries}."
            )
    except Exception:
        logger.exception(
            "create_goal: unexpected error. user_id=%s goal_text=%r",
            user_id, goal_text,
        )
        raise


@tool
def get_goals() -> str:
    """Return all active goals and their actions.
    Returns a JSON list of goals, each with a flat 'actions' list."""
    user_id = get_request_user_id()
    return json.dumps(goals_analytics.get_goals_with_actions(user_id))


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
def check_compliance() -> str:
    """Check weekly compliance for all active goal actions.
    Returns a JSON summary of actual vs target values for each action this week."""
    user_id = get_request_user_id()
    return json.dumps(compliance_analytics.run_compliance_check(user_id))


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

    try:
        action_id_int = int(action_id)
    except (ValueError, TypeError):
        return f"Invalid action_id '{action_id}'. Must be a numeric ID."

    user_id = get_request_user_id()
    set_clause = ", ".join(f"{k} = %s" for k in updates) + ", updated_at = NOW()"
    values = list(updates.values()) + [action_id_int, user_id]

    try:
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
                    (action_id_int, week_start, user_id),
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
                        (target_float, met, action_id_int, week_start, user_id),
                    )

            return json.dumps({
                "updated": True,
                "action_id": action_id_int,
                "action_text": result["action_text"],
                "condition": result["condition"],
                "target_value": float(result["target_value"]),
                "frequency": result["frequency"],
            })
    except Exception:
        logger.exception(
            "update_action: unexpected error. user_id=%s action_id=%r updates=%r",
            user_id, action_id, updates,
        )
        raise


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
