import datetime

from db.schema import get_connection


def get_food_entries(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
    meal_group: str | None = None,
) -> list[dict]:
    """Individual food items logged in Cronometer (Servings export).
    Optionally filtered by date range (YYYY-MM-DD) and/or meal group.
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)
    if meal_group is not None:
        conditions.append("meal_group = %s")
        params.append(meal_group)
    sql = """
        SELECT date, logged_at, meal_group, food_name, amount, category,
               energy_kcal, protein_g, carbs_g, net_carbs_g, fat_g, fiber_g,
               sugars_g, sodium_mg, potassium_mg, calcium_mg, iron_mg, vitamin_d_iu
        FROM nutrition_foods
        WHERE """ + " AND ".join(conditions) + """
        ORDER BY date, logged_at
    """
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_nutrition(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Macros and key performance micros per day from Cronometer.
    Optionally filtered by date range (YYYY-MM-DD).
    Defaults to the last 60 days when no date range is provided."""
    if since is None and until is None:
        since = (datetime.date.today() - datetime.timedelta(days=60)).isoformat()
    conditions = ["user_id = %s"]
    params: list = [user_id]
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
        WHERE """ + " AND ".join(conditions)
    sql += " ORDER BY date"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
