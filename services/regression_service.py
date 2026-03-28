import math

import numpy as np
from scipy import stats


def run_regression(x_values: list, y_values: list) -> dict:
    """Run simple linear regression on paired x/y values.

    Filters None and NaN values before computing. Requires at least 5 clean pairs.
    Returns slope, intercept, r_squared, p_value, std_err, significant, sample_size, direction.
    """
    cleaned = [
        (x, y)
        for x, y in zip(x_values, y_values)
        if isinstance(x, (int, float))
        and isinstance(y, (int, float))
        and not math.isnan(x)
        and not math.isnan(y)
    ]
    if len(cleaned) < 5:
        return {"error": "insufficient_data", "min_required": 5, "actual": len(cleaned)}

    x_arr = np.array([pair[0] for pair in cleaned], dtype=float)
    y_arr = np.array([pair[1] for pair in cleaned], dtype=float)

    try:
        slope, intercept, r_value, p_value, std_err = stats.linregress(x_arr, y_arr)
    except Exception as e:
        return {"error": "computation_failed", "detail": str(e)}

    return {
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": float(r_value ** 2),
        "p_value": float(p_value),
        "std_err": float(std_err),
        "significant": bool(p_value < 0.05),
        "sample_size": len(cleaned),
        "direction": "positive" if slope > 0 else "negative",
    }


def assess_insight_confidence(regression_result: dict) -> str | None:
    """Map regression result to insight confidence level.

    Returns 'strong', 'moderate', or None (do not derive insight).
    """
    if "error" in regression_result:
        return None
    if not regression_result.get("significant"):
        return None

    r_squared = regression_result["r_squared"]
    sample_size = regression_result["sample_size"]

    if r_squared > 0.5 and sample_size >= 20:
        return "strong"
    if r_squared > 0.25 and sample_size >= 10:
        return "moderate"
    return None


def generate_interpretation(x_col: str, y_col: str, regression_result: dict) -> str:
    """Generate a human-readable interpretation of the regression result.

    Uses natural units derived from column name suffixes:
    _g -> 10 (grams), _minutes -> 60 (minutes), _milli -> 1000 (milliseconds), else 1.
    """
    unit_size: float
    if "_g" in x_col:
        unit_size = 10.0
        unit_label = "10g"
    elif "_minutes" in x_col:
        unit_size = 60.0
        unit_label = "60 minutes (1 hour)"
    elif "_milli" in x_col:
        unit_size = 1000.0
        unit_label = "1000ms"
    elif "_kcal" in x_col:
        unit_size = 100.0
        unit_label = "100 kcal"
    else:
        unit_size = 1.0
        unit_label = "1 unit"

    slope = regression_result["slope"]
    y_delta = slope * unit_size
    x_label = x_col.replace("_", " ")
    y_label = y_col.replace("_", " ")

    return (
        f"Each additional {unit_label} of {x_label} is associated with "
        f"a {y_delta:+.2f} change in {y_label}."
    )
