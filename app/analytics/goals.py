from db.schema import get_connection


def get_active_goals(user_id: int) -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM goals WHERE user_id = %s AND status = 'active' ORDER BY created_at",
            (user_id,),
        ).fetchall()


def get_active_insights(user_id: int) -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM insights WHERE user_id = %s AND status = 'active' "
            "ORDER BY pinned DESC, date_derived DESC",
            (user_id,),
        ).fetchall()


def get_insight_by_tool(user_id: int, correlative_tool: str) -> dict | None:
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM insights WHERE user_id = %s AND correlative_tool = %s AND status = 'active'",
            (user_id, correlative_tool),
        ).fetchone()


def get_goals_with_actions(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id AS goal_id, g.user_id AS g_user_id, g.session_id AS g_session_id,
                g.raw_input, g.goal_text, g.title, g.domains, g.target_date,
                g.status AS g_status, g.created_at AS g_created_at, g.updated_at AS g_updated_at,
                a.id AS action_id, a.user_id AS a_user_id,
                a.action_text, a.metric, a.condition, a.target_value,
                a.data_source, a.frequency, a.created_at AS a_created_at
            FROM goals g
            LEFT JOIN actions a ON a.goal_id = g.id
            WHERE g.user_id = %s AND g.status = 'active'
            ORDER BY g.id, a.id
            """,
            (user_id,),
        ).fetchall()

        goals_map: dict = {}
        for row in rows:
            gid = row["goal_id"]
            if gid not in goals_map:
                goals_map[gid] = {
                    "id": gid,
                    "user_id": row["g_user_id"],
                    "session_id": row["g_session_id"],
                    "raw_input": row["raw_input"],
                    "goal_text": row["goal_text"],
                    "title": row["title"],
                    "domains": row["domains"],
                    "target_date": row["target_date"],
                    "status": row["g_status"],
                    "created_at": row["g_created_at"],
                    "updated_at": row["g_updated_at"],
                    "actions": [],
                }
            if row["action_id"] is not None:
                goals_map[gid]["actions"].append({
                    "id": row["action_id"],
                    "goal_id": gid,
                    "user_id": row["a_user_id"],
                    "action_text": row["action_text"],
                    "metric": row["metric"],
                    "condition": row["condition"],
                    "target_value": row["target_value"],
                    "data_source": row["data_source"],
                    "frequency": row["frequency"],
                    "created_at": row["a_created_at"],
                })
        return list(goals_map.values())
