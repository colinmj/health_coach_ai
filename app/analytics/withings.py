from db.schema import get_connection


def get_body_composition(
    user_id: int,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Body composition measurements, optionally filtered by date range (YYYY-MM-DD)."""
    conditions = ["user_id = %s"]
    params: list = [user_id]
    if since is not None:
        conditions.append("date >= %s")
        params.append(since)
    if until is not None:
        conditions.append("date <= %s")
        params.append(until)
    sql = """
        SELECT date, weight_kg, fat_ratio, muscle_mass_kg, fat_free_mass_kg, bone_mass_kg
        FROM body_measurements
        WHERE """ + " AND ".join(conditions)
    sql += " ORDER BY date"
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
