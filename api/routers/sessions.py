import json

from fastapi import APIRouter, HTTPException

from db.schema import get_connection, get_local_user_id

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
def list_sessions() -> list[dict]:
    user_id = get_local_user_id()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, created_at, updated_at
            FROM sessions
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return list(rows)


@router.get("/{session_id}/messages")
def get_session_messages(session_id: int) -> list[dict]:
    user_id = get_local_user_id()
    with get_connection() as conn:
        # Verify session belongs to this user
        session = conn.execute(
            "SELECT id FROM sessions WHERE id = %s AND user_id = %s",
            (session_id, user_id),
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        rows = conn.execute(
            """
            SELECT role, content
            FROM messages
            WHERE session_id = %s AND role IN ('human', 'ai')
            ORDER BY id
            """,
            (session_id,),
        ).fetchall()

    messages = []
    for row in rows:
        d = json.loads(row["content"])
        raw = d.get("data", {}).get("content", "")

        if isinstance(raw, list):
            text = " ".join(
                block.get("text", "")
                for block in raw
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
        else:
            text = (raw or "").strip()

        if text:
            messages.append({"role": row["role"], "text": text})

    return messages
