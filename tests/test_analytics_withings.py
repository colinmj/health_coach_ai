"""Tests for analytics/withings.py query functions."""

import analytics.withings as withings


class TestGetBodyComposition:
    def test_returns_all_measurements(self, db):
        rows = withings.get_body_composition()
        assert len(rows) == 2

    def test_ordered_by_date_ascending(self, db):
        rows = withings.get_body_composition()
        dates = [r["date"] for r in rows]
        assert dates == sorted(dates)

    def test_filter_by_since(self, db):
        rows = withings.get_body_composition(since="2024-01-15")
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-17"

    def test_filter_by_until(self, db):
        rows = withings.get_body_composition(until="2024-01-12")
        assert len(rows) == 1
        assert rows[0]["date"] == "2024-01-10"

    def test_fields_present(self, db):
        rows = withings.get_body_composition()
        row = rows[0]
        assert row["weight_kg"] == 82.0
        assert row["fat_ratio"] == 0.18
        assert row["muscle_mass_kg"] == 38.0
