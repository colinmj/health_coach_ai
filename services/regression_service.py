import math

import numpy as np
from scipy import stats
from sklearn.linear_model import LinearRegression


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


def run_multiple_regression(rows: list[dict], x_cols: list[str], y_col: str) -> dict:
    """Run multiple linear regression on a dataset with multiple predictors.

    rows: list of dicts (e.g. from a correlation tool).
    x_cols: list of column names to use as predictors.
    y_col: column name for the outcome variable.

    Filters rows with any None/NaN/non-numeric value in x_cols or y_col.
    Requires at least 10 clean rows. Returns r_squared, adj_r_squared,
    coefficients, standardized_coefficients (beta — for feature importance),
    p_values per feature, significant_features, sample_size, predictors, outcome.
    """
    cleaned = []
    for row in rows:
        try:
            x_vals = [float(row[c]) for c in x_cols]
            y_val = float(row[y_col])
            if any(math.isnan(v) for v in x_vals) or math.isnan(y_val):
                continue
            cleaned.append((x_vals, y_val))
        except (TypeError, ValueError, KeyError):
            continue

    n = len(cleaned)
    p = len(x_cols)

    if n < 10:
        return {"error": "insufficient_data", "min_required": 10, "actual": n}
    if n <= p + 1:
        return {
            "error": "insufficient_data_for_predictors",
            "detail": f"Need more than {p + 1} rows for {p} predictors, got {n}",
        }

    X = np.array([c[0] for c in cleaned], dtype=float)
    y = np.array([c[1] for c in cleaned], dtype=float)

    model = LinearRegression().fit(X, y)
    y_pred = model.predict(X)
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r_squared = (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - p - 1)

    # OLS p-values per feature via t-statistics
    df_res = n - p - 1
    mse = ss_res / df_res
    try:
        XtX_inv = np.linalg.inv(X.T @ X)
        se = np.sqrt(mse * np.diag(XtX_inv))
        t_stats = model.coef_ / se
        p_values = [float(2 * (1 - stats.t.cdf(abs(t), df=df_res))) for t in t_stats]
    except np.linalg.LinAlgError:
        return {"error": "computation_failed", "detail": "singular matrix — predictors may be collinear"}

    # Standardized (beta) coefficients for feature importance comparison
    x_std = X.std(axis=0)
    y_std = float(y.std())
    if y_std > 0:
        std_coefs = [(float(model.coef_[i]) * float(x_std[i]) / y_std) for i in range(p)]
    else:
        std_coefs = [0.0] * p

    significant_features = [x_cols[i] for i, pv in enumerate(p_values) if pv < 0.05]

    return {
        "r_squared": round(r_squared, 4),
        "adj_r_squared": round(adj_r_squared, 4),
        "sample_size": n,
        "predictors": x_cols,
        "outcome": y_col,
        "coefficients": {x_cols[i]: round(float(model.coef_[i]), 4) for i in range(p)},
        "standardized_coefficients": {x_cols[i]: round(std_coefs[i], 4) for i in range(p)},
        "p_values": {x_cols[i]: round(p_values[i], 4) for i in range(p)},
        "significant_features": significant_features,
        "intercept": round(float(model.intercept_), 4),
    }


def generate_multi_interpretation(regression_result: dict) -> str:
    """Generate a human-readable interpretation of a multiple regression result.

    Ranks features by absolute standardized coefficient (beta) and describes
    relative importance. Always uses "associated with" framing.
    """
    if "error" in regression_result:
        return "Insufficient data to determine feature importance."

    std_coefs = regression_result.get("standardized_coefficients", {})
    outcome = regression_result.get("outcome", "the outcome").replace("_", " ")

    if not std_coefs:
        return f"No predictors found for {outcome}."

    ranked = sorted(std_coefs.items(), key=lambda kv: abs(kv[1]), reverse=True)

    if len(ranked) == 1:
        name, beta = ranked[0]
        direction = "positively" if beta > 0 else "negatively"
        return (
            f"{name.replace('_', ' ')} (β={beta:+.2f}) is the only significant predictor "
            f"and is {direction} associated with {outcome}."
        )

    top_name, top_beta = ranked[0]
    second_name, second_beta = ranked[1]
    ratio = abs(top_beta) / abs(second_beta) if second_beta != 0 else float("inf")

    parts = [f"{name.replace('_', ' ')} (β={beta:+.2f})" for name, beta in ranked[:3]]
    top_label = top_name.replace("_", " ")
    second_label = second_name.replace("_", " ")

    return (
        f"The strongest predictors of {outcome} are {', '.join(parts)}. "
        f"{top_label.capitalize()} is associated with the largest effect, "
        f"with {ratio:.1f}x the impact of {second_label}."
    )
