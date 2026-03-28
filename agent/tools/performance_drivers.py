import json

from langchain_core.tools import tool

import analytics.performance_drivers as pd_analytics
from api.feature_gates import Feature, check_tool_feature
from api.tool_confirmation import check_confirmation, fingerprint, record_invocation
from db.schema import get_connection, get_request_user_id
from services import regression_service

_X_COLS = [
    "hrv_rmssd_milli",
    "recovery_score",
    "sleep_minutes",
    "sleep_efficiency",
    "protein_g",
    "carbs_g",
    "energy_kcal",
]
_Y_COL = "performance_score"


@tool
def get_performance_drivers(since: str = "", until: str = "") -> str:
    """Use for 'what drives my workout performance?' or 'which factor matters most
    for my training?' questions.

    Fetches workout performance paired with prior-day sleep, HRV, recovery score,
    and nutrition in a single query, then immediately runs multiple regression to
    identify which predictors are most strongly associated with performance score.

    More efficient than calling a correlation tool + analyze_multi_correlation
    separately — returns the full analysis in one call.

    since/until are optional YYYY-MM-DD date strings.

    Returns:
    - regression: r_squared, adj_r_squared, standardized_coefficients (beta),
                  p_values, significant_features, insight_confidence, interpretation
    - data_summary: date_range, n_workouts, available_predictors (those with >= 5 values)
    - raw_rows: the paired dataset (for narrating trends)

    Predictors analysed: hrv_rmssd_milli, recovery_score, sleep_minutes,
    sleep_efficiency, protein_g, carbs_g, energy_kcal vs performance_score (0-3 scale).
    ALWAYS use "associated with" framing — NEVER imply causation.
    """
    if err := check_tool_feature(Feature.MULTIPLE_REGRESSION):
        return err

    input_hash = fingerprint(f"performance_drivers|{since}|{until}")
    check_confirmation("multiple_regression", input_hash)

    user_id = get_request_user_id()
    with get_connection() as conn:
        rows = pd_analytics.get_performance_drivers(
            user_id=user_id,
            conn=conn,
            since=since.strip() or None,
            until=until.strip() or None,
        )

    if not rows:
        return json.dumps({"error": "no_data", "detail": "No workout data found for the given date range."})

    # Run multiple regression
    regression = regression_service.run_multiple_regression(rows, _X_COLS, _Y_COL)

    confidence = None
    interpretation = ""
    if "error" not in regression:
        confidence = regression_service.assess_insight_confidence(regression)
        interpretation = regression_service.generate_multi_interpretation(regression)

    # Build data summary
    dates = [r["workout_date"] for r in rows if r.get("workout_date")]
    available_predictors = [
        col for col in _X_COLS
        if sum(1 for r in rows if r.get(col) is not None) >= 5
    ]

    data_summary = {
        "n_workouts": len(rows),
        "date_range": {
            "from": str(min(dates)) if dates else None,
            "to": str(max(dates)) if dates else None,
        },
        "available_predictors": available_predictors,
    }

    output = json.dumps(
        {
            "regression": {
                **regression,
                "insight_confidence": confidence,
                "interpretation": interpretation,
            },
            "data_summary": data_summary,
            "raw_rows": [
                {k: (str(v) if hasattr(v, "isoformat") else v) for k, v in row.items()}
                for row in rows
            ],
        },
        default=str,
    )
    record_invocation("multiple_regression", input_hash, output)
    return output
