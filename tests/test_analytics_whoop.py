"""Tests for analytics/whoop.py query functions."""

import analytics.whoop as whoop


class TestGetRecovery:
    def test_returns_only_scored_rows(self, db):
        rows = whoop.get_recovery()
        assert len(rows) == 2
        assert all("recovery_score" in r for r in rows)

    def test_ordered_by_date_ascending(self, db):
        rows = whoop.get_recovery()
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)

    def test_filter_by_since(self, db):
        rows = whoop.get_recovery(since="2024-01-16")
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-16"

    def test_filter_by_until(self, db):
        rows = whoop.get_recovery(until="2024-01-09")
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-09"

    def test_fields_present(self, db):
        rows = whoop.get_recovery()
        row = rows[0]
        assert row["hrv_rmssd_milli"] == 65.0
        assert row["resting_heart_rate"] == 52.0


class TestGetSleep:
    def test_excludes_naps_by_default(self, db):
        rows = whoop.get_sleep()
        assert len(rows) == 2

    def test_filter_by_since(self, db):
        rows = whoop.get_sleep(since="2024-01-16")
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-16"

    def test_sleep_fields_present(self, db):
        rows = whoop.get_sleep()
        row = rows[0]
        assert row["sleep_performance_percentage"] == 88.0
        assert row["sleep_efficiency_percentage"] == 91.0
        assert row["total_in_bed_time_milli"] == 28800000
