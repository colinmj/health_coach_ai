"""Tests for analytics/goals.py query functions."""

import analytics.goals as goals


def test_get_active_goals_returns_seeded_goals(db):
    ids = db._test_ids
    result = goals.get_active_goals(ids["user_id"])
    assert len(result) == 2
    goal_ids = {g["id"] for g in result}
    assert ids["goal_id"] in goal_ids
    assert ids["goal2_id"] in goal_ids
    assert all(g["status"] == "active" for g in result)


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
    assert len(result) == 2
    goals_by_id = {g["id"]: g for g in result}

    # Complex goal — has protocol with actions, no direct actions
    g1 = goals_by_id[ids["goal_id"]]
    assert len(g1["protocols"]) == 1
    assert g1["protocols"][0]["id"] == ids["protocol_id"]
    assert len(g1["protocols"][0]["actions"]) == 2
    assert g1["direct_actions"] == []

    # Simple goal — no protocols, has direct actions
    g2 = goals_by_id[ids["goal2_id"]]
    assert g2["protocols"] == []
    assert len(g2["direct_actions"]) == 1
    assert g2["direct_actions"][0]["id"] == ids["direct_action_id"]
    assert g2["direct_actions"][0]["metric"] == "fiber_g"


def test_get_active_direct_actions(db):
    ids = db._test_ids
    result = goals.get_active_direct_actions(ids["user_id"])
    assert len(result) == 1
    assert result[0]["id"] == ids["direct_action_id"]
    assert result[0]["goal_id"] == ids["goal2_id"]


def test_get_active_protocols_with_actions(db):
    ids = db._test_ids
    result = goals.get_active_protocols_with_actions(ids["user_id"])
    assert len(result) == 1
    assert result[0]["id"] == ids["protocol_id"]
    assert len(result[0]["actions"]) == 2
