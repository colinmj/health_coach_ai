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


def get_active_protocols_with_actions(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                p.id AS protocol_id, p.user_id AS p_user_id, p.session_id AS p_session_id,
                p.goal_id, p.insight_ids, p.protocol_text, p.start_date, p.review_date,
                p.status AS p_status, p.outcome, p.created_at AS p_created_at,
                p.updated_at AS p_updated_at,
                a.id AS action_id, a.protocol_id AS a_protocol_id, a.user_id AS a_user_id,
                a.action_text, a.metric, a.condition, a.target_value,
                a.data_source, a.frequency, a.created_at AS a_created_at
            FROM protocols p
            LEFT JOIN actions a ON a.protocol_id = p.id
            WHERE p.user_id = %s AND p.status = 'active'
            ORDER BY p.id, a.id
            """,
            (user_id,),
        ).fetchall()

        protocols: dict = {}
        for row in rows:
            pid = row["protocol_id"]
            if pid not in protocols:
                protocols[pid] = {
                    "id": row["protocol_id"],
                    "user_id": row["p_user_id"],
                    "session_id": row["p_session_id"],
                    "goal_id": row["goal_id"],
                    "insight_ids": row["insight_ids"],
                    "protocol_text": row["protocol_text"],
                    "start_date": row["start_date"],
                    "review_date": row["review_date"],
                    "status": row["p_status"],
                    "outcome": row["outcome"],
                    "created_at": row["p_created_at"],
                    "updated_at": row["p_updated_at"],
                    "actions": [],
                }
            if row["action_id"] is not None:
                protocols[pid]["actions"].append({
                    "id": row["action_id"],
                    "protocol_id": row["a_protocol_id"],
                    "user_id": row["a_user_id"],
                    "action_text": row["action_text"],
                    "metric": row["metric"],
                    "condition": row["condition"],
                    "target_value": row["target_value"],
                    "data_source": row["data_source"],
                    "frequency": row["frequency"],
                    "created_at": row["a_created_at"],
                })
        return list(protocols.values())


def get_goals_with_protocols_and_actions(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                g.id AS goal_id, g.user_id AS g_user_id, g.session_id AS g_session_id,
                g.raw_input, g.goal_text, g.domains, g.target_date,
                g.status AS g_status, g.created_at AS g_created_at, g.updated_at AS g_updated_at,
                p.id AS protocol_id, p.user_id AS p_user_id, p.session_id AS p_session_id,
                p.goal_id AS p_goal_id, p.insight_ids, p.protocol_text, p.start_date, p.review_date,
                p.status AS p_status, p.outcome, p.created_at AS p_created_at,
                p.updated_at AS p_updated_at,
                a.id AS action_id, a.protocol_id AS a_protocol_id, a.user_id AS a_user_id,
                a.action_text, a.metric, a.condition, a.target_value,
                a.data_source, a.frequency, a.created_at AS a_created_at,
                da.id AS da_id, da.user_id AS da_user_id,
                da.action_text AS da_action_text, da.metric AS da_metric,
                da.condition AS da_condition, da.target_value AS da_target_value,
                da.data_source AS da_data_source, da.frequency AS da_frequency,
                da.created_at AS da_created_at
            FROM goals g
            LEFT JOIN protocols p ON p.goal_id = g.id
            LEFT JOIN actions a ON a.protocol_id = p.id
            LEFT JOIN actions da ON da.goal_id = g.id AND da.protocol_id IS NULL
            WHERE g.user_id = %s AND g.status = 'active'
            ORDER BY g.id, p.id, a.id, da.id
            """,
            (user_id,),
        ).fetchall()

        goals_map: dict = {}
        for row in rows:
            gid = row["goal_id"]
            if gid not in goals_map:
                goals_map[gid] = {
                    "id": row["goal_id"],
                    "user_id": row["g_user_id"],
                    "session_id": row["g_session_id"],
                    "raw_input": row["raw_input"],
                    "goal_text": row["goal_text"],
                    "domains": row["domains"],
                    "target_date": row["target_date"],
                    "status": row["g_status"],
                    "created_at": row["g_created_at"],
                    "updated_at": row["g_updated_at"],
                    "protocols": {},
                    "direct_actions": {},
                }
            if row["protocol_id"] is not None:
                protocols = goals_map[gid]["protocols"]
                pid = row["protocol_id"]
                if pid not in protocols:
                    protocols[pid] = {
                        "id": row["protocol_id"],
                        "user_id": row["p_user_id"],
                        "session_id": row["p_session_id"],
                        "goal_id": row["p_goal_id"],
                        "insight_ids": row["insight_ids"],
                        "protocol_text": row["protocol_text"],
                        "start_date": row["start_date"],
                        "review_date": row["review_date"],
                        "status": row["p_status"],
                        "outcome": row["outcome"],
                        "created_at": row["p_created_at"],
                        "updated_at": row["p_updated_at"],
                        "actions": [],
                    }
                if row["action_id"] is not None:
                    protocols[pid]["actions"].append({
                        "id": row["action_id"],
                        "protocol_id": row["a_protocol_id"],
                        "user_id": row["a_user_id"],
                        "action_text": row["action_text"],
                        "metric": row["metric"],
                        "condition": row["condition"],
                        "target_value": row["target_value"],
                        "data_source": row["data_source"],
                        "frequency": row["frequency"],
                        "created_at": row["a_created_at"],
                    })
            if row["da_id"] is not None:
                goals_map[gid]["direct_actions"][row["da_id"]] = {
                    "id": row["da_id"],
                    "goal_id": gid,
                    "user_id": row["da_user_id"],
                    "action_text": row["da_action_text"],
                    "metric": row["da_metric"],
                    "condition": row["da_condition"],
                    "target_value": row["da_target_value"],
                    "data_source": row["da_data_source"],
                    "frequency": row["da_frequency"],
                    "created_at": row["da_created_at"],
                }

        result = []
        for g in goals_map.values():
            g["protocols"] = list(g["protocols"].values())
            g["direct_actions"] = list(g["direct_actions"].values())
            result.append(g)
        return result


def get_active_direct_actions(user_id: int) -> list[dict]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT a.*
            FROM actions a
            JOIN goals g ON g.id = a.goal_id
            WHERE a.user_id = %s AND a.goal_id IS NOT NULL AND g.status = 'active'
            ORDER BY a.id
            """,
            (user_id,),
        ).fetchall()
