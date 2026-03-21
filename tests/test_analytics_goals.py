"""Tests for analytics/goals.py query functions."""

import analytics.goals as goals


def test_get_active_goals_returns_seeded_goal(db):
    ids = db._test_ids
    result = goals.get_active_goals(ids["user_id"])
    assert len(result) == 1
    assert result[0]["id"] == ids["goal_id"]
    assert result[0]["status"] == "active"
    assert "strength" in result[0]["goal_text"].lower() or result[0]["goal_text"]


def test_get_active_insights_pinned_first(db):
    ids = db._test_ids
    # Seed has one pinned + one unpinned insight
    result = goals.get_active_insights(ids["user_id"])
    assert len(result) == 2
    # Pinned insight should come first
    assert result[0]["pinned"] is True
    assert result[1]["pinned"] is False


def test_get_insight_by_tool_returns_none_for_unknown_tool(db):
    ids = db._test_ids
    result = goals.get_insight_by_tool(ids["user_id"], "nonexistent_tool")
    assert result is None


def test_get_insight_by_tool_returns_existing(db):
    ids = db._test_ids
    result = goals.get_insight_by_tool(ids["user_id"], "get_sleep_vs_performance")
    assert result is not None
    assert result["correlative_tool"] == "get_sleep_vs_performance"


def test_get_goals_with_protocols_and_actions(db):
    ids = db._test_ids
    result = goals.get_goals_with_protocols_and_actions(ids["user_id"])
    assert len(result) == 1
    g = result[0]
    assert g["id"] == ids["goal_id"]
    assert len(g["protocols"]) == 1
    p = g["protocols"][0]
    assert p["id"] == ids["protocol_id"]
    assert len(p["actions"]) == 2


def test_get_active_protocols_with_actions(db):
    ids = db._test_ids
    result = goals.get_active_protocols_with_actions(ids["user_id"])
    assert len(result) == 1
    assert result[0]["id"] == ids["protocol_id"]
    assert len(result[0]["actions"]) == 2
