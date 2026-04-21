"""Tests for analytics/trends.py."""

import datetime
from unittest.mock import patch

import analytics.trends as trends


# The seeded data spans 2024-01-09 to 2024-01-17.
# We set as_of = 2024-01-18 (Friday) so the last-7-days window is 2024-01-11–2024-01-17
# and the prior-7-days window is 2024-01-04–2024-01-11.
# This puts:
#   - recovery rows for 2024-01-09 and 2024-01-16 → both in the 14-day range
#   - sleep rows for 2024-01-09 and 2024-01-16   → both in the 14-day range
#   - workouts on 2024-01-10 (prior) and 2024-01-17 (current)
#   - nutrition on 2024-01-09/10 (prior) and 2024-01-16/17 (current)
AS_OF = datetime.date(2024, 1, 18)


def test_build_trends_block_returns_string(db):
    ids = db._test_ids
    result = trends.build_trends_block(ids["user_id"], as_of=AS_OF)
    assert isinstance(result, str)


def test_trends_block_contains_header(db):
    ids = db._test_ids
    result = trends.build_trends_block(ids["user_id"], as_of=AS_OF)
    assert "Trends" in result
    assert "2024-01-18" in result


def test_trends_block_includes_recovery(db):
    ids = db._test_ids
    result = trends.build_trends_block(ids["user_id"], as_of=AS_OF)
    # Seeded: recovery_score 85 (2024-01-09, prior window) and 42 (2024-01-16, current window)
    assert "Recovery score" in result
    assert "42" in result


def test_trends_block_includes_workouts(db):
    ids = db._test_ids
    result = trends.build_trends_block(ids["user_id"], as_of=AS_OF)
    assert "Workouts" in result


def test_trends_block_includes_nutrition(db):
    ids = db._test_ids
    result = trends.build_trends_block(ids["user_id"], as_of=AS_OF)
    assert "protein" in result.lower()
    assert "calories" in result.lower()


def test_trends_block_empty_for_no_data(db):
    """A user with no data at all should get an empty string."""
    from db.schema import get_connection
    # Use a user_id that has no rows
    result = trends.build_trends_block(user_id=99999, as_of=AS_OF)
    assert result == ""
