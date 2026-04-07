"""Tests for analytics/compliance.py and db/queries/metrics.py."""

import datetime

import analytics.compliance as compliance
from db.queries.metrics import fetch_all_metrics


# ---------------------------------------------------------------------------
# db.queries.metrics — fetch_all_metrics
# ---------------------------------------------------------------------------

def test_fetch_nutrition_metric_avg(db):
    """fetch_all_metrics returns AVG of protein_g over a seeded week."""
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"protein_g"}, week_start, week_end)
    # Seeded: 160g on 2024-01-09, 180g on 2024-01-10 → AVG = 170
    assert metrics["protein_g"] is not None
    assert abs(float(metrics["protein_g"]) - 170.0) < 0.01


def test_fetch_workout_frequency_seeded(db):
    """fetch_all_metrics counts distinct workout days."""
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"workout_frequency"}, week_start, week_end)
    # Seeded: one workout on 2024-01-10 in that week
    assert metrics["workout_frequency"] == 1.0


def test_fetch_activity_frequency_no_data_returns_zero(db):
    """fetch_all_metrics returns 0.0 (not None) for activity_frequency when no matching rows."""
    ids = db._test_ids
    week_start = datetime.date(2023, 1, 2)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"activity_frequency"}, week_start, week_end)
    assert metrics["activity_frequency"] == 0.0


def test_fetch_all_metrics_batches_activity_metrics(db):
    """Both activity_frequency and running_frequency are fetched in a single query."""
    ids = db._test_ids
    week_start = datetime.date(2023, 1, 2)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(
        db, ids["user_id"], {"activity_frequency", "running_frequency"}, week_start, week_end
    )
    assert "activity_frequency" in metrics
    assert "running_frequency" in metrics


# ---------------------------------------------------------------------------
# compliance._met — condition logic
# ---------------------------------------------------------------------------

def test_met_greater_than():
    assert compliance._met(170.0, 150.0, "greater_than") is True
    assert compliance._met(140.0, 150.0, "greater_than") is False


def test_met_less_than():
    assert compliance._met(900.0, 1000.0, "less_than") is True
    assert compliance._met(1100.0, 1000.0, "less_than") is False


def test_met_equals():
    assert compliance._met(100.0, 100.0, "equals") is True
    assert compliance._met(100.0, 99.0,  "equals") is False


def test_met_none_actual_returns_none():
    assert compliance._met(None, 100.0, "greater_than") is None


# ---------------------------------------------------------------------------
# Nutrition + workout conditions via fetch_all_metrics
# ---------------------------------------------------------------------------

def test_fetch_nutrition_avg_meets_target(db):
    """Protein avg over seeded week meets a greater_than target."""
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"protein_g"}, week_start, week_end)
    # avg of 160 and 180 = 170 > 150 → met
    assert compliance._met(metrics["protein_g"], 150.0, "greater_than") is True


def test_fetch_nutrition_no_data_returns_none(db):
    """When no nutrition rows fall in the window, value should be None."""
    ids = db._test_ids
    week_start = datetime.date(2023, 1, 2)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"calories"}, week_start, week_end)
    assert metrics["calories"] is None
    assert compliance._met(metrics["calories"], 2000.0, "less_than") is None


def test_fetch_calories_condition_less_than(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"calories"}, week_start, week_end)
    # avg calories is >2000 → less_than 1000 should be False
    assert compliance._met(metrics["calories"], 1000.0, "less_than") is False


def test_fetch_calories_condition_greater_than(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"calories"}, week_start, week_end)
    # avg calories is ~2350 → greater_than 2000 should be True
    assert compliance._met(metrics["calories"], 2000.0, "greater_than") is True


def test_workout_frequency_met(db):
    ids = db._test_ids
    week_start = datetime.date(2024, 1, 8)
    week_end = week_start + datetime.timedelta(days=7)
    metrics = fetch_all_metrics(db, ids["user_id"], {"workout_frequency"}, week_start, week_end)
    # Seeded workout on 2024-01-10 → count = 1
    assert metrics["workout_frequency"] == 1.0
    assert compliance._met(metrics["workout_frequency"], 0.0, "greater_than") is True


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
