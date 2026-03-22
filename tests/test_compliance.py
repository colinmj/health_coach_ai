"""Tests for analytics/compliance.py and db/queries/metrics.py."""

import datetime

import analytics.compliance as compliance
from db.queries.metrics import (
    fetch_nutrition_metric,
    fetch_workout_frequency,
    fetch_activity_frequency,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_action(ids, metric, condition, target_value, data_source="cronometer", frequency="daily"):
    return {
        "id": ids["action1_id"],
        "protocol_id": ids["protocol_id"],
        "user_id": ids["user_id"],
        "action_text": "test action",
        "metric": metric,
        "condition": condition,
        "target_value": target_value,
        "data_source": data_source,
        "frequency": frequency,
    }


# ---------------------------------------------------------------------------
# db.queries.metrics — fetcher functions in isolation
# ---------------------------------------------------------------------------

def test_fetch_nutrition_metric_avg(db):
    """fetch_nutrition_metric returns AVG of protein_g over a seeded week."""
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    val = fetch_nutrition_metric(db, ids["user_id"], "protein_g", week_start, week_end)
    # Seeded: 160g on 2024-01-09, 180g on 2024-01-10 → AVG = 170
    assert val is not None
    assert abs(float(val) - 170.0) < 0.01


def test_fetch_workout_frequency_seeded(db):
    """fetch_workout_frequency counts distinct workout days."""
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    val = fetch_workout_frequency(db, ids["user_id"], week_start, week_end)
    # Seeded: one workout on 2024-01-10 in that week
    assert val == 1.0


def test_fetch_activity_frequency_no_data_returns_zero(db):
    """fetch_activity_frequency returns 0.0 (not None) when no matching rows."""
    ids = db._test_ids
    week_start = datetime.date(2023, 1, 2)
    week_end = week_start + datetime.timedelta(days=7)
    val = fetch_activity_frequency(db, ids["user_id"], week_start, week_end)
    assert val == 0.0


# ---------------------------------------------------------------------------
# compute_compliance_for_action
# ---------------------------------------------------------------------------

def test_compute_nutrition_avg(db):
    """Protein average over the seeded week should be computable."""
    ids = db._test_ids
    # Seeded data: 2024-01-09 (160g) and 2024-01-10 (180g) in the week of 2024-01-08 (Mon)
    week_start = datetime.date(2024, 1, 8)
    action = _make_action(ids, "protein_g", "greater_than", 150.0)
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["actual_value"] is not None
    assert result["actual_value"] > 0
    # avg of 160 and 180 = 170 > 150 → met
    assert result["met"] is True


def test_compute_nutrition_no_data_returns_none(db):
    """When no nutrition rows fall in the window, actual_value and met should be None."""
    ids = db._test_ids
    week_start = datetime.date(2023, 1, 2)  # no data in this week
    action = _make_action(ids, "calories", "less_than", 2000.0)
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["actual_value"] is None
    assert result["met"] is None


def test_condition_less_than(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    # avg calories for that week is >2000 → less_than 1000 should be False
    action = _make_action(ids, "calories", "less_than", 1000.0)
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["met"] is False


def test_condition_greater_than(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    # avg calories is ~2350 → greater_than 2000 should be True
    action = _make_action(ids, "calories", "greater_than", 2000.0)
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["met"] is True


def test_condition_equals(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    action = _make_action(ids, "calories", "equals", 9999.0)
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["met"] is False


def test_workout_frequency(db):
    ids = db._test_ids
    # Seeded workout on 2024-01-10 → count = 1 in that week
    week_start = datetime.date(2024, 1, 8)
    action = _make_action(ids, "workout_frequency", "greater_than", 0.0, data_source="hevy", frequency="weekly")
    result = compliance.compute_compliance_for_action(db, action, week_start)
    assert result["actual_value"] == 1.0
    assert result["met"] is True


# ---------------------------------------------------------------------------
# run_compliance_check — upsert idempotency
# ---------------------------------------------------------------------------

def test_run_compliance_check_upsert_no_duplicates(db):
    """Running compliance check twice for the same week updates existing row (no duplicates)."""
    from unittest.mock import patch
    import datetime as dt

    ids = db._test_ids
    fixed_today = dt.date(2024, 1, 15)  # Monday

    with patch("analytics.compliance.date") as mock_date:
        mock_date.today.return_value = fixed_today
        mock_date.side_effect = lambda *a, **kw: dt.date(*a, **kw)

        compliance.run_compliance_check(ids["user_id"])
        compliance.run_compliance_check(ids["user_id"])

    count = db.execute(
        "SELECT COUNT(*) AS n FROM action_compliance WHERE user_id = %s",
        (ids["user_id"],),
    ).fetchone()["n"]
    # 2 protocol actions + 1 direct action × 1 week = 3 rows (no duplicates)
    assert count == 3


def test_run_compliance_check_includes_direct_actions(db):
    """run_compliance_check includes direct goal actions (no protocol) in results."""
    from unittest.mock import patch
    import datetime as dt

    ids = db._test_ids
    fixed_today = dt.date(2024, 1, 15)  # Monday

    with patch("analytics.compliance.date") as mock_date:
        mock_date.today.return_value = fixed_today
        mock_date.side_effect = lambda *a, **kw: dt.date(*a, **kw)

        results = compliance.run_compliance_check(ids["user_id"])

    direct = [r for r in results if r["protocol_id"] is None]
    assert len(direct) == 1
    assert direct[0]["action_id"] == ids["direct_action_id"]
    assert direct[0]["goal_id"] == ids["goal2_id"]
    assert direct[0]["metric"] == "fiber_g"


def test_run_compliance_check_protocol_filter_excludes_direct_actions(db):
    """When filtering by protocol_id, direct actions are not included."""
    from unittest.mock import patch
    import datetime as dt

    ids = db._test_ids
    fixed_today = dt.date(2024, 1, 15)  # Monday

    with patch("analytics.compliance.date") as mock_date:
        mock_date.today.return_value = fixed_today
        mock_date.side_effect = lambda *a, **kw: dt.date(*a, **kw)

        results = compliance.run_compliance_check(ids["user_id"], protocol_id=ids["protocol_id"])

    assert all(r["protocol_id"] == ids["protocol_id"] for r in results)
    assert len(results) == 2
