import pytest
from services.regression_service import (
    assess_insight_confidence,
    generate_interpretation,
    run_regression,
)
from services.regression_service import (
    generate_multi_interpretation,
    run_multiple_regression,
)


# --- run_regression ---

def test_run_regression_known_values():
    x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0]
    result = run_regression(x, y)
    assert result["slope"] == pytest.approx(2.0, abs=1e-6)
    assert result["r_squared"] == pytest.approx(1.0, abs=1e-6)
    assert result["p_value"] < 0.05
    assert result["significant"] is True
    assert result["direction"] == "positive"
    assert result["sample_size"] == 10


def test_run_regression_negative_slope():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [10.0, 8.0, 6.0, 4.0, 2.0]
    result = run_regression(x, y)
    assert result["slope"] < 0
    assert result["direction"] == "negative"


def test_run_regression_insufficient_data():
    result = run_regression([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    assert result["error"] == "insufficient_data"
    assert result["min_required"] == 5


def test_run_regression_filters_nulls():
    x = [1.0, None, 3.0, 4.0, 5.0, 6.0]
    y = [2.0, 4.0, None, 8.0, 10.0, 12.0]
    result = run_regression(x, y)
    # None pairs filtered: (1,2), (6,12) survive + (4,8), (5,10) = 4 clean pairs — insufficient
    assert result["error"] == "insufficient_data"


def test_run_regression_filters_nulls_enough_data():
    x = [1.0, None, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0]
    result = run_regression(x, y)
    # (1,2) filtered because None in x; remaining 7 pairs are clean
    assert "error" not in result
    assert result["sample_size"] == 7


def test_run_regression_all_nulls():
    x = [None, None, None, None, None]
    y = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = run_regression(x, y)
    assert result["error"] == "insufficient_data"


# --- assess_insight_confidence ---

def test_assess_confidence_strong():
    result = {
        "significant": True,
        "r_squared": 0.65,
        "sample_size": 25,
        "p_value": 0.001,
    }
    assert assess_insight_confidence(result) == "strong"


def test_assess_confidence_moderate():
    result = {
        "significant": True,
        "r_squared": 0.35,
        "sample_size": 12,
        "p_value": 0.02,
    }
    assert assess_insight_confidence(result) == "moderate"


def test_assess_confidence_not_significant():
    result = {
        "significant": False,
        "r_squared": 0.8,
        "sample_size": 30,
        "p_value": 0.2,
    }
    assert assess_insight_confidence(result) is None


def test_assess_confidence_low_r_squared():
    result = {
        "significant": True,
        "r_squared": 0.1,
        "sample_size": 30,
        "p_value": 0.04,
    }
    assert assess_insight_confidence(result) is None


def test_assess_confidence_insufficient_sample_for_strong():
    result = {
        "significant": True,
        "r_squared": 0.6,
        "sample_size": 15,  # needs 20 for strong
        "p_value": 0.01,
    }
    assert assess_insight_confidence(result) == "moderate"


def test_assess_confidence_error_dict():
    result = {"error": "insufficient_data", "min_required": 5}
    assert assess_insight_confidence(result) is None


# --- generate_interpretation ---

def test_generate_interpretation_grams():
    result = {"slope": 0.008}
    interp = generate_interpretation("carbs_g", "performance_score", result)
    assert "10g" in interp
    assert "associated with" in interp
    assert "+0.08" in interp


def test_generate_interpretation_minutes():
    result = {"slope": 0.5}
    interp = generate_interpretation("prior_night_in_bed_minutes", "performance_score", result)
    assert "60 minutes" in interp
    assert "+30.00" in interp


def test_generate_interpretation_milli():
    result = {"slope": 0.04}
    interp = generate_interpretation("prior_night_hrv_milli", "performance_score", result)
    assert "1000ms" in interp
    assert "+40.00" in interp


# --- run_multiple_regression ---

def _make_rows(n=20):
    """Make rows where y = 2*x1 + 3*x2 + noise."""
    import random
    random.seed(42)
    rows = []
    for i in range(n):
        x1 = float(i)
        x2 = float(i * 0.5 + random.uniform(-0.1, 0.1))
        y = 2.0 * x1 + 3.0 * x2 + random.uniform(-0.5, 0.5)
        rows.append({"x1": x1, "x2": x2, "y": y})
    return rows


def test_run_multiple_regression_high_r_squared():
    rows = _make_rows(20)
    result = run_multiple_regression(rows, ["x1", "x2"], "y")
    assert "error" not in result
    assert result["r_squared"] > 0.95
    assert result["sample_size"] == 20
    assert "x1" in result["coefficients"]
    assert "x2" in result["coefficients"]
    assert "x1" in result["standardized_coefficients"]


def test_run_multiple_regression_insufficient_rows():
    rows = _make_rows(8)
    result = run_multiple_regression(rows, ["x1", "x2"], "y")
    assert result["error"] == "insufficient_data"
    assert result["min_required"] == 10


def test_run_multiple_regression_too_many_predictors():
    rows = _make_rows(10)
    # 10 rows, 10 predictors → n <= p+1
    x_cols = [f"x{i}" for i in range(10)]
    for row in rows:
        for col in x_cols:
            row[col] = 1.0
    result = run_multiple_regression(rows, x_cols, "y")
    assert result["error"] == "insufficient_data_for_predictors"


def test_run_multiple_regression_filters_nulls():
    rows = _make_rows(20)
    rows[0]["x1"] = None  # one row has a null predictor
    result = run_multiple_regression(rows, ["x1", "x2"], "y")
    assert "error" not in result
    assert result["sample_size"] == 19


def test_run_multiple_regression_p_values_present():
    rows = _make_rows(20)
    result = run_multiple_regression(rows, ["x1", "x2"], "y")
    assert "p_values" in result
    assert "x1" in result["p_values"]
    assert "x2" in result["p_values"]
    assert all(0.0 <= v <= 1.0 for v in result["p_values"].values())


# --- generate_multi_interpretation ---

def test_generate_multi_interpretation_contains_associated_with():
    result = {
        "standardized_coefficients": {"hrv": 0.5, "protein": 0.25},
        "outcome": "performance_score",
    }
    interp = generate_multi_interpretation(result)
    assert "associated with" in interp


def test_generate_multi_interpretation_names_top_predictor():
    result = {
        "standardized_coefficients": {"hrv": 0.5, "protein": 0.25},
        "outcome": "performance_score",
    }
    interp = generate_multi_interpretation(result)
    assert "hrv" in interp


def test_generate_multi_interpretation_error_input():
    result = {"error": "insufficient_data"}
    interp = generate_multi_interpretation(result)
    assert "Insufficient" in interp
