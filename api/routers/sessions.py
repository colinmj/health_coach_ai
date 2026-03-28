import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/")
def list_sessions(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, summary, pinned, created_at, updated_at
            FROM sessions
            WHERE user_id = %s
            ORDER BY pinned DESC, updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return list(rows)


class UpdateSessionBody(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


@router.patch("/{session_id}")
def update_session(
    session_id: int,
    body: UpdateSessionBody,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    # Build SET clause from a hardcoded whitelist only.
    # Use sentinel check (is not None) so pinned=False correctly unpins a session.
    allowed_fields = {"title": body.title, "pinned": body.pinned}
    updates = {k: v for k, v in allowed_fields.items() if v is not None}

    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields provided")

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [session_id, user_id]

    with get_connection() as conn:
        row = conn.execute(
            f"""
            UPDATE sessions
            SET {set_clause}, updated_at = NOW()
            WHERE id = %s AND user_id = %s
            RETURNING id, title, summary, pinned, created_at, updated_at
            """,
            values,
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        conn.commit()

    return dict(row)


@router.delete("/{session_id}")
def delete_session(
    session_id: int,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM sessions WHERE id = %s AND user_id = %s RETURNING id",
            (session_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        conn.commit()

    return {"deleted": True}


@router.get("/{session_id}/messages")
def get_session_messages(session_id: int, user_id: int = Depends(get_current_user_id)) -> list[dict]:
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
