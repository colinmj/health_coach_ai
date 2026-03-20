from db.schema import get_connection


def get_nutrition(
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Macros and key performance micros per day from Cronometer.
    Optionally filtered by date range (YYYY-MM-DD)."""
    conditions = []
    params: list = []
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)
    sql = """
        SELECT date, source, energy_kcal, protein_g, carbs_g, net_carbs_g, fat_g,
               fiber_g, sugars_g, magnesium_mg, sodium_mg, potassium_mg,
               vitamin_d_iu, iron_mg, calcium_mg, completed
        FROM nutrition_daily
    """
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY date"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
