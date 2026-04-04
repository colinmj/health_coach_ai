"""Tests for analytics/correlations.py query functions."""

import analytics.correlations as corr


class TestGetHrvVsPerformance:
    def test_returns_one_row_per_workout(self, db):
        rows = corr.get_hrv_vs_performance(since="2024-01-01")
        assert len(rows) == 2

    def test_high_hrv_night_before_good_workout(self, db):
        rows = corr.get_hrv_vs_performance(since="2024-01-01")
        row = next(r for r in rows if r["workout_date"] == "2024-01-10")
        assert row["prior_night_hrv_milli"] == 65.0
        assert row["best_tag"] == "PR"

    def test_low_hrv_night_before_worse_workout(self, db):
        rows = corr.get_hrv_vs_performance(since="2024-01-01")
        row = next(r for r in rows if r["workout_date"] == "2024-01-17")
        assert row["prior_night_hrv_milli"] == 38.0

    def test_filter_by_since(self, db):
        rows = corr.get_hrv_vs_performance(since="2024-01-15")
        assert len(rows) == 1
        assert rows[0]["workout_date"] == "2024-01-17"

    def test_no_recovery_data_excluded(self, db):
        # Filter to a range with no matching recovery row → empty
        rows = corr.get_hrv_vs_performance(since="2024-02-01")
        assert rows == []


class TestGetSleepVsPerformance:
    def test_returns_one_row_per_workout(self, db):
        rows = corr.get_sleep_vs_performance(since="2024-01-01")
        assert len(rows) == 2

    def test_sleep_durations_in_minutes(self, db):
        rows = corr.get_sleep_vs_performance(since="2024-01-01")
        row = next(r for r in rows if r["workout_date"] == "2024-01-10")
        # 28800000ms = 480 minutes
        assert row["prior_night_in_bed_minutes"] == 480.0

    def test_filter_by_until(self, db):
        rows = corr.get_sleep_vs_performance(until="2024-01-12")
        assert len(rows) == 1
        assert rows[0]["workout_date"] == "2024-01-10"


class TestGetSleepThresholdVsPerformance:
    def test_returns_two_groups(self, db):
        rows = corr.get_sleep_threshold_vs_performance(threshold_hours=7.0, since="2024-01-01")
        groups = {r["sleep_group"] for r in rows}
        assert groups == {"above_threshold", "below_threshold"}

    def test_correct_grouping_at_8_hours(self, db):
        # slp-1 = 8h (above), slp-2 = 6h (below) for threshold=7h
        rows = corr.get_sleep_threshold_vs_performance(threshold_hours=7.0, since="2024-01-01")
        by_group = {r["sleep_group"]: r for r in rows}
        assert by_group["above_threshold"]["workout_count"] == 1
        assert by_group["below_threshold"]["workout_count"] == 1

    def test_threshold_higher_than_all_sleep(self, db):
        # threshold=9h → both nights below
        rows = corr.get_sleep_threshold_vs_performance(threshold_hours=9.0, since="2024-01-01")
        by_group = {r["sleep_group"]: r for r in rows}
        assert "above_threshold" not in by_group
        assert by_group["below_threshold"]["workout_count"] == 2

    def test_threshold_lower_than_all_sleep(self, db):
        # threshold=5h → both nights above
        rows = corr.get_sleep_threshold_vs_performance(threshold_hours=5.0, since="2024-01-01")
        by_group = {r["sleep_group"]: r for r in rows}
        assert "below_threshold" not in by_group
        assert by_group["above_threshold"]["workout_count"] == 2


class TestGetBodyCompositionVsStrength:
    def test_returns_one_row_per_measurement(self, db):
        rows = corr.get_body_composition_vs_strength(since="2024-01-01")
        assert len(rows) == 2

    def test_matches_same_day_workout(self, db):
        rows = corr.get_body_composition_vs_strength(since="2024-01-01")
        row = next(r for r in rows if r["measurement_date"] == "2024-01-10")
        assert row["nearest_workout_date"] == "2024-01-10"
        assert row["weight_kg"] == 82.0

    def test_no_match_outside_window(self, db):
        # window=0 days — measurement and workout must be on the exact same day
        rows = corr.get_body_composition_vs_strength(days_window=0, since="2024-01-01")
        assert len(rows) == 2  # both measurements share a date with a workout

    def test_filter_by_since(self, db):
        rows = corr.get_body_composition_vs_strength(since="2024-01-15")
        assert len(rows) == 1
        assert rows[0]["measurement_date"] == "2024-01-17"
