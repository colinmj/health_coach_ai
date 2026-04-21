from datetime import date, timedelta

from db.schema import get_connection
from analytics.goals import get_goals_with_actions
from db.queries.metrics import fetch_all_metrics


def _met(actual, target, condition: str) -> bool | None:
    if actual is None:
        return None
    if condition == "less_than":
        return actual < target
    if condition == "greater_than":
        return actual > target
    if condition == "equals":
        return abs(actual - target) < 0.001
    return None


def _week_window() -> tuple[date, date]:
    today = date.today()
    week_start = today - timedelta(days=today.weekday())  # most recent Monday
    week_end = week_start + timedelta(days=7)
    return week_start, week_end


def run_compliance_check(user_id: int) -> list[dict]:
    """Check compliance for all active goal actions.

    Fetches all required metrics in at most 3 queries using FILTER clauses,
    then upserts action_compliance rows. Returns a summary list.
    """
    week_start, week_end = _week_window()

    goals = get_goals_with_actions(user_id)
    all_actions = [a for g in goals for a in g.get("actions", [])]

    if not all_actions:
        return []

    needed_metrics = {a["metric"] for a in all_actions}

    results = []
    with get_connection() as conn:
        # Single batched fetch — at most 3 queries for all metrics
        metrics = fetch_all_metrics(conn, user_id, needed_metrics, week_start, week_end)

        for action in all_actions:
            actual = metrics.get(action["metric"])
            met = _met(actual, float(action["target_value"]), action["condition"])

            conn.execute(
                """
                INSERT INTO action_compliance
                    (action_id, user_id, week_start_date, target_value, actual_value, met, checked_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (action_id, week_start_date) DO UPDATE
                    SET actual_value = EXCLUDED.actual_value,
                        met = EXCLUDED.met,
                        checked_at = NOW()
                """,
                (action["id"], user_id, week_start, action["target_value"], actual, met),
            )

            results.append({
                "goal_id": action["goal_id"],
                "action_id": action["id"],
                "action_text": action["action_text"],
                "metric": action["metric"],
                "condition": action["condition"],
                "target_value": float(action["target_value"]),
                "actual_value": actual,
                "met": met,
                "week_start_date": week_start.isoformat(),
            })

    return results
