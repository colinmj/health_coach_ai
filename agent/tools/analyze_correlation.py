import json

from langchain_core.tools import tool

from api.feature_gates import Feature, check_tool_feature
from api.tool_confirmation import check_confirmation, fingerprint, record_invocation
from services import regression_service


@tool
def analyze_correlation(rows_json: str, x_col: str, y_col: str) -> str:
    """Run linear regression on a correlation dataset already fetched by a correlation tool.

    rows_json: the JSON string returned by a correlation tool (pass it directly).
    x_col: the column name to use as the independent variable (predictor).
    y_col: the column name to use as the dependent variable (outcome).

    Returns a JSON object with: x, y, slope, intercept, r_squared, p_value, std_err,
    significant, direction, sample_size, insight_confidence, interpretation.
    If there is insufficient data (fewer than 5 paired non-null values), returns an error object.

    Use this after calling a correlation tool when you want to quantify the relationship
    for insight derivation. Do NOT use with get_sleep_threshold_vs_performance or
    get_carbs_prior_to_prs — those return aggregated data, not paired rows.

    Common x_col / y_col pairs:
    - get_hrv_vs_performance:          prior_night_hrv_milli / performance_score
    - get_sleep_vs_performance:        prior_night_in_bed_minutes / performance_score
    - get_body_composition_vs_strength: fat_ratio / avg_1rm_kg_across_exercises
    - get_nutrition_vs_performance:    carbs_g / performance_score
    - get_protein_vs_strength:         protein_g / avg_session_1rm_kg
    - get_nutrition_vs_recovery:       prior_day_carbs_g / recovery_score
    - get_nutrition_vs_activity:       prior_night_carbs_g / strain
    - get_activity_vs_strength:        prior_day_strain / performance_score
    - get_nutrition_vs_body_composition: energy_kcal / fat_ratio
    - get_energy_balance_vs_weight:    rolling_7d_avg_balance / actual_7d_weight_change_kg
    """
    if err := check_tool_feature(Feature.LINEAR_REGRESSION):
        return err

    input_hash = fingerprint(f"{rows_json}|{x_col}|{y_col}")
    check_confirmation("linear_regression", input_hash)

    try:
        rows = json.loads(rows_json)
    except (json.JSONDecodeError, TypeError) as e:
        return json.dumps({"error": "invalid_json", "detail": str(e)})

    if not isinstance(rows, list):
        return json.dumps({"error": "expected_list", "detail": "rows_json must be a JSON array"})

    x_values = [row.get(x_col) for row in rows]
    y_values = [row.get(y_col) for row in rows]

    result = regression_service.run_regression(x_values, y_values)
    if "error" in result:
        return json.dumps({"x": x_col, "y": y_col, **result})

    confidence = regression_service.assess_insight_confidence(result)
    interpretation = regression_service.generate_interpretation(x_col, y_col, result)

    output = json.dumps({
        "x": x_col,
        "y": y_col,
        **result,
        "insight_confidence": confidence,
        "interpretation": interpretation,
    })
    record_invocation("linear_regression", input_hash, output)
    return output
