"""Tests for pure functions in sync/hevy.py."""

import pytest
from sync.hevy import epley_1rm, tag_performance


# ---------------------------------------------------------------------------
# epley_1rm
# ---------------------------------------------------------------------------

class TestEpley1rm:
    def test_single_rep_returns_weight(self):
        assert epley_1rm(100.0, 1) == 100.0

    def test_standard_calculation(self):
        # 100kg × (1 + 5/30) = 116.67
        assert epley_1rm(100.0, 5) == 116.67

    def test_zero_reps_returns_none(self):
        assert epley_1rm(100.0, 0) is None

    def test_zero_weight_returns_none(self):
        assert epley_1rm(0.0, 5) is None

    def test_none_weight_returns_none(self):
        assert epley_1rm(None, 5) is None

    def test_none_reps_returns_none(self):
        assert epley_1rm(100.0, None) is None


# ---------------------------------------------------------------------------
# tag_performance
# ---------------------------------------------------------------------------

class TestTagPerformance:
    def test_no_prior_history_is_baseline(self):
        assert tag_performance(100.0, prev_best=None, all_time_best=None) == "Baseline"

    def test_beats_all_time_best_is_pr(self):
        assert tag_performance(110.0, prev_best=100.0, all_time_best=105.0) == "PR"

    def test_more_than_2_5_percent_above_prev_is_better(self):
        # prev=100, current=103 → ratio=1.03 > 1.025
        assert tag_performance(103.0, prev_best=100.0, all_time_best=110.0) == "Better"

    def test_within_2_5_percent_is_neutral(self):
        # prev=100, current=101 → ratio=1.01, within ±2.5%
        assert tag_performance(101.0, prev_best=100.0, all_time_best=110.0) == "Neutral"

    def test_exactly_at_threshold_is_neutral(self):
        # prev=100, current=102.5 → ratio=1.025, not strictly greater
        assert tag_performance(102.5, prev_best=100.0, all_time_best=110.0) == "Neutral"

    def test_more_than_2_5_percent_below_prev_is_worse(self):
        # prev=100, current=97 → ratio=0.97 < 0.975
        assert tag_performance(97.0, prev_best=100.0, all_time_best=110.0) == "Worse"

    def test_none_1rm_is_neutral(self):
        assert tag_performance(None, prev_best=100.0, all_time_best=110.0) == "Neutral"

    def test_no_prev_session_but_has_all_time_is_neutral(self):
        # Has done the exercise before, but not the session before this one
        assert tag_performance(100.0, prev_best=None, all_time_best=110.0) == "Neutral"
