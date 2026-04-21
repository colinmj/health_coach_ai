"""Tests for analytics/hevy.py query functions."""

import analytics.hevy as hevy


class TestGetExercisePrs:
    def test_returns_one_pr_per_exercise(self, db):
        rows = hevy.get_exercise_prs(db._test_ids["user_id"])
        ids = [r["exercise_template_id"] for r in rows]
        assert sorted(ids) == ["bench-001", "squat-001"]

    def test_pr_is_highest_1rm(self, db):
        rows = hevy.get_exercise_prs(db._test_ids["user_id"], exercise_template_id="bench-001")
        assert len(rows) == 1
        # workout 2 bench (99.17) beats workout 1 (93.33)
        assert rows[0]["pr_1rm_kg"] == 99.17

    def test_filter_by_template_id(self, db):
        rows = hevy.get_exercise_prs(db._test_ids["user_id"], exercise_template_id="squat-001")
        assert len(rows) == 1
        assert rows[0]["exercise_title"] == "Squat"

    def test_unknown_exercise_returns_empty(self, db):
        rows = hevy.get_exercise_prs(db._test_ids["user_id"], exercise_template_id="does-not-exist")
        assert rows == []


class TestGetWorkout1rmHistory:
    def test_returns_all_sessions(self, db):
        rows = hevy.get_workout_1rm_history(db._test_ids["user_id"])
        # 2 workouts × 2 exercises = 4 rows
        assert len(rows) == 4

    def test_filter_by_exercise(self, db):
        rows = hevy.get_workout_1rm_history(db._test_ids["user_id"], exercise_template_id="bench-001")
        assert len(rows) == 2
        assert all(r["exercise_template_id"] == "bench-001" for r in rows)

    def test_filter_by_since(self, db):
        rows = hevy.get_workout_1rm_history(db._test_ids["user_id"], since="2024-01-15")
        assert len(rows) == 2
        assert all(r["workout_date"] >= "2024-01-15" for r in rows)

    def test_filter_by_until(self, db):
        rows = hevy.get_workout_1rm_history(db._test_ids["user_id"], until="2024-01-12")
        assert len(rows) == 2
        assert all(r["workout_date"] <= "2024-01-12" for r in rows)


class TestGetWorkoutPerformance:
    def test_returns_one_row_per_workout(self, db):
        rows = hevy.get_workout_performance(db._test_ids["user_id"])
        assert len(rows) == 2

    def test_performance_tags_counted_correctly(self, db):
        rows = hevy.get_workout_performance(db._test_ids["user_id"])
        # Sorted newest-first by the view
        w2 = next(r for r in rows if r["workout_date"] == "2024-01-17")
        assert w2["better_sets"] == 1
        assert w2["worse_sets"] == 1
        assert w2["pr_sets"] == 0

        w1 = next(r for r in rows if r["workout_date"] == "2024-01-10")
        assert w1["pr_sets"] == 2

    def test_filter_by_min_score(self, db):
        # Workout 1: all PRs → score=3.0; workout 2: Better+Worse → score=1.0
        rows = hevy.get_workout_performance(db._test_ids["user_id"], min_score=2.0)
        assert len(rows) == 1
        assert rows[0]["workout_date"] == "2024-01-10"


class TestGetExerciseTemplateIds:
    def test_returns_both_exercises(self, db):
        rows = hevy.get_exercise_template_ids(db._test_ids["user_id"])
        ids = {r["exercise_template_id"] for r in rows}
        assert ids == {"bench-001", "squat-001"}

    def test_session_count_is_correct(self, db):
        rows = hevy.get_exercise_template_ids(db._test_ids["user_id"])
        by_id = {r["exercise_template_id"]: r for r in rows}
        assert by_id["bench-001"]["session_count"] == 2
        assert by_id["squat-001"]["session_count"] == 2
