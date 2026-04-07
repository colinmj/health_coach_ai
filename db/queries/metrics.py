"""Batched metric fetcher used by analytics/compliance.py.

fetch_all_metrics runs at most 3 queries (one per source table) regardless of
how many metrics are needed, using FILTER clauses to combine activity metrics.
"""
from datetime import timedelta


def fetch_all_metrics(
    conn,
    user_id: int,
    needed: set[str],
    week_start,
    week_end,
) -> dict[str, float | None]:
    """Fetch all needed metrics in at most 3 queries.

    Returns a dict mapping metric name -> value (or None if no data).
    Metrics not present in `needed` are omitted from the result.
    """
    results: dict[str, float | None] = {}

    # Nutrition — one query covering all four nutrition columns
    _NUTRITION_COLS = {
        "calories":  "energy_kcal",
        "protein_g": "protein_g",
        "carbs_g":   "carbs_g",
        "fat_g":     "fat_g",
    }
    if needed & _NUTRITION_COLS.keys():
        row = conn.execute(
            """
            SELECT
                AVG(energy_kcal) AS calories,
                AVG(protein_g)   AS protein_g,
                AVG(carbs_g)     AS carbs_g,
                AVG(fat_g)       AS fat_g
            FROM nutrition_daily
            WHERE user_id = %s AND date >= %s AND date < %s
            """,
            (user_id, week_start, week_end),
        ).fetchone()
        for metric in needed & _NUTRITION_COLS.keys():
            results[metric] = row[metric] if row else None

    # Workout frequency
    if "workout_frequency" in needed:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT start_time::date) AS val
            FROM hevy_workouts
            WHERE user_id = %s AND start_time::date >= %s AND start_time::date < %s
            """,
            (user_id, week_start, week_end),
        ).fetchone()
        results["workout_frequency"] = float(row["val"]) if row and row["val"] is not None else 0.0

    # Activity metrics — combined with FILTER to avoid a second table scan
    if needed & {"activity_frequency", "running_frequency"}:
        row = conn.execute(
            """
            SELECT
                COUNT(*)                                              AS activity_frequency,
                COUNT(*) FILTER (WHERE sport_name ILIKE '%%running%%') AS running_frequency
            FROM activities
            WHERE user_id = %s AND date >= %s AND date < %s
            """,
            (user_id, week_start, week_end),
        ).fetchone()
        if "activity_frequency" in needed:
            results["activity_frequency"] = float(row["activity_frequency"]) if row else 0.0
        if "running_frequency" in needed:
            results["running_frequency"] = float(row["running_frequency"]) if row else 0.0

    return results
