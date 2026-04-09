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


def test_get_goals_with_actions(db):
    ids = db._test_ids
    result = goals.get_goals_with_actions(ids["user_id"])
    assert len(result) == 2
    goals_by_id = {g["id"]: g for g in result}

    # First goal — has two direct actions
    g1 = goals_by_id[ids["goal_id"]]
    assert len(g1["actions"]) == 2
    action_ids = {a["id"] for a in g1["actions"]}
    assert ids["action1_id"] in action_ids
    assert ids["action2_id"] in action_ids

    # Second goal — has one direct action
    g2 = goals_by_id[ids["goal2_id"]]
    assert len(g2["actions"]) == 1
    assert g2["actions"][0]["id"] == ids["direct_action_id"]
    assert g2["actions"][0]["metric"] == "fiber_g"
