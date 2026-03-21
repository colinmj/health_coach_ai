from datetime import date, timedelta

import psycopg

from db.schema import get_connection
from analytics.goals import get_active_protocols_with_actions
from db.queries.metrics import (
    fetch_nutrition_metric,
    fetch_workout_frequency,
    fetch_activity_frequency,
    fetch_running_frequency,
)


# ---------------------------------------------------------------------------
# Canonical metric → (table, column, aggregation) mapping
# ---------------------------------------------------------------------------

_NUTRITION_METRICS: dict[str, str] = {
    "calories":   "energy_kcal",
    "protein_g":  "protein_g",
    "carbs_g":    "carbs_g",
    "fat_g":      "fat_g",
}

_FREQUENCY_METRICS = {"workout_frequency", "activity_frequency", "running_frequency"}


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


def compute_compliance_for_action(
    conn: psycopg.Connection,
    action: dict,
    week_start: date,
) -> dict:
    """Compute actual_value and met for a single action over the given week window."""
    week_end = week_start + timedelta(days=7)
    metric = action["metric"]
    condition = action["condition"]
    target = float(action["target_value"])
    user_id = action["user_id"]

    if metric in _NUTRITION_METRICS:
        actual = fetch_nutrition_metric(conn, user_id, _NUTRITION_METRICS[metric], week_start, week_end)
    elif metric == "workout_frequency":
        actual = fetch_workout_frequency(conn, user_id, week_start, week_end)
    elif metric == "activity_frequency":
        actual = fetch_activity_frequency(conn, user_id, week_start, week_end)
    elif metric == "running_frequency":
        actual = fetch_running_frequency(conn, user_id, week_start, week_end)
    else:
        actual = None

    return {
        "actual_value": actual,
        "met": _met(actual, target, condition),
    }


def run_compliance_check(
    user_id: int,
    protocol_id: int | None = None,
) -> list[dict]:
    """Check compliance for all active protocols/actions (or a specific protocol).
    Upserts action_compliance rows. Returns summary list."""
    week_start, _ = _week_window()
    results = []

    with get_connection() as conn:
        protocols = get_active_protocols_with_actions(user_id)
        if protocol_id is not None:
            protocols = [p for p in protocols if p["id"] == protocol_id]

        for protocol in protocols:
            for action in protocol.get("actions", []):
                computed = compute_compliance_for_action(conn, action, week_start)
                actual = computed["actual_value"]
                met = computed["met"]

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
                    "protocol_id": protocol["id"],
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
