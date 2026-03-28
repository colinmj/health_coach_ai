import json

from langchain_core.tools import tool

from api.feature_gates import Feature, check_tool_feature
from api.tool_confirmation import check_confirmation, fingerprint, record_invocation
from services import regression_service


@tool
def analyze_multi_correlation(rows_json: str, x_cols_json: str, y_col: str) -> str:
    """Run multiple linear regression to find which combination of variables best
    predicts an outcome, and their relative importance (feature importance).

    rows_json: the JSON string returned directly by a correlation tool.
    x_cols_json: a JSON array of predictor column names as a string,
                 e.g. '["prior_night_hrv_milli", "prior_night_in_bed_minutes"]'
    y_col: the outcome column name, e.g. "performance_score"

    Returns r_squared, adj_r_squared, standardized_coefficients (beta values —
    directly comparable as feature importance), p_values per feature,
    significant_features, sample_size, and a plain-English interpretation.

    Requires at least 10 clean rows (rows where all columns are non-null numeric).

    Use this when the user asks which of several factors matters most, or to
    compare relative impact of multiple predictors on a single outcome.
    ALWAYS use "associated with" — NEVER "causes". Regression shows correlation only.

    Suggested predictor sets (x_cols_json) and data sources:

    Predicting performance_score:
    - '["prior_night_hrv_milli", "prior_night_in_bed_minutes", "prior_night_recovery_score"]'
      → use data from get_hrv_vs_performance or get_sleep_vs_performance
    - '["carbs_g", "protein_g", "energy_kcal"]'
      → use data from get_nutrition_vs_performance

    Predicting recovery_score:
    - '["prior_day_carbs_g", "prior_day_protein_g", "prior_day_energy_kcal"]'
      → use data from get_nutrition_vs_recovery

    Predicting avg_session_1rm_kg:
    - '["protein_g", "carbs_g", "energy_kcal"]'
      → use data from get_protein_vs_strength
    """
    if err := check_tool_feature(Feature.MULTIPLE_REGRESSION):
        return err

    input_hash = fingerprint(f"{rows_json}|{x_cols_json}|{y_col}")
    check_confirmation("multiple_regression", input_hash)

    try:
        rows = json.loads(rows_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": "invalid_json", "detail": str(e)})

    if not isinstance(rows, list):
        return json.dumps({"error": "expected_list", "detail": "rows_json must be a JSON array"})

    try:
        x_cols = json.loads(x_cols_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": "invalid_x_cols_json", "detail": str(e)})

    if not isinstance(x_cols, list) or len(x_cols) < 2:
        return json.dumps({
            "error": "invalid_x_cols",
            "detail": "x_cols_json must be a JSON array with at least 2 column names",
        })

    result = regression_service.run_multiple_regression(rows, x_cols, y_col)
    if "error" in result:
        return json.dumps(result)

    confidence = regression_service.assess_insight_confidence(result)
    interpretation = regression_service.generate_multi_interpretation(result)

    output = json.dumps({
        **result,
        "insight_confidence": confidence,
        "interpretation": interpretation,
    })
    record_invocation("multiple_regression", input_hash, output)
    return output
