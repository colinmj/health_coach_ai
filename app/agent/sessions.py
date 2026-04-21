"""Session and message persistence for the LangGraph agent.

Each session is a conversation thread. Messages are stored as JSON-serialized
LangChain message dicts so they can be round-tripped through messages_from_dict
and fed back into create_react_agent as full history.
"""

import json

from langchain_core.messages import messages_to_dict, messages_from_dict, HumanMessage, ToolMessage

from db.schema import get_connection


def create_session(user_id: int, title: str, session_type: str = "chat") -> int:
    """Create a new session and return its id. Title is truncated to 120 chars."""
    with get_connection() as conn:
        row = conn.execute(
            "INSERT INTO sessions (user_id, title, session_type) VALUES (%s, %s, %s) RETURNING id",
            (user_id, title[:120], session_type),
        ).fetchone()
        assert row is not None
        return row["id"]


def _compress_history(messages: list, max_tool_chars: int = 1500) -> list:
    """Replace oversized ToolMessage content with a truncated summary.

    Keeps the first max_tool_chars of each ToolMessage so the agent
    retains context about which tool was called and the shape of the result,
    while avoiding the token bloat of replaying full JSON datasets.
    """
    compressed = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and len(str(msg.content)) > max_tool_chars:
            content = str(msg.content)
            summary = content[:max_tool_chars] + f"\n[... {len(content) - max_tool_chars} chars truncated from history]"
            msg = ToolMessage(content=summary, tool_call_id=msg.tool_call_id)
        compressed.append(msg)
    return compressed


_HISTORY_MESSAGE_LIMIT = 60  # ~15 ReAct turns (human + AI-plan + tool-result + AI-response per turn)


def load_messages(session_id: int) -> list:
    """Return recent messages for a session as LangChain message objects, ordered oldest-first.

    Caps at _HISTORY_MESSAGE_LIMIT to prevent input-token bloat on long sessions.
    Tool message content is further truncated by _compress_history.
    """
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT content FROM messages WHERE session_id = %s ORDER BY id DESC LIMIT %s",
            (session_id, _HISTORY_MESSAGE_LIMIT),
        ).fetchall()
    if not rows:
        return []
    # fetchall returned newest-first; reverse to restore chronological order
    rows = list(reversed(rows))
    messages = messages_from_dict([json.loads(r["content"]) for r in rows])

    # If history was trimmed mid-session, the first message may be a ToolMessage or
    # mid-sequence AIMessage — Anthropic requires every tool_result to have a preceding
    # tool_use. Trim to the first HumanMessage to guarantee a clean turn boundary.
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            messages = messages[i:]
            break

    return _compress_history(messages)


def append_messages(session_id: int, new_messages: list) -> None:
    """Persist a list of new LangChain message objects to the messages table."""
    dicts = messages_to_dict(new_messages)
    with get_connection() as conn:
        for d in dicts:
            role = d["type"]  # human | ai | tool
            tool_name = d.get("data", {}).get("name") if role == "tool" else None
            conn.execute(
                "INSERT INTO messages (session_id, role, content, tool_name) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, role, json.dumps(d), tool_name),
            )


def save_summary(session_id: int, summary: str) -> None:
    """Save or update the summary for a session."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE sessions SET summary = %s, updated_at = NOW() WHERE id = %s",
            (summary, session_id),
        )


def get_recent_context(user_id: int, exclude_session_id: int | None = None) -> str:
    """Return a formatted excerpt of the most recent prior session for cross-session memory.

    Filters to human and AI messages only (skips tool call/result noise).
    Only includes AI messages that have actual text content (skips pure tool-dispatch steps).
    Returns an empty string if no prior sessions exist.
    """
    with get_connection() as conn:
        query = (
            "SELECT id, title FROM sessions WHERE user_id = %s AND session_type = 'chat'"
            + (" AND id != %s" if exclude_session_id is not None else "")
            + " ORDER BY created_at DESC LIMIT 1"
        )
        params = (user_id, exclude_session_id) if exclude_session_id is not None else (user_id,)
        session = conn.execute(query, params).fetchone()
        if not session:
            return ""

        rows = conn.execute(
            "SELECT role, content FROM messages "
            "WHERE session_id = %s AND role IN ('human', 'ai') "
            "ORDER BY id DESC LIMIT 16",
            (session["id"],),
        ).fetchall()

    if not rows:
        return ""

    lines = [f"## Most recent session: \"{session['title']}\"\n"]
    turns = 0
    for row in reversed(rows):
        if turns >= 8:
            break
        d = json.loads(row["content"])
        raw_content = d.get("data", {}).get("content", "")

        # AI messages with tool_calls have content as a list of blocks; extract text only
        if isinstance(raw_content, list):
            text = " ".join(
                block.get("text", "")
                for block in raw_content
                if isinstance(block, dict) and block.get("type") == "text"
            ).strip()
        else:
            text = (raw_content or "").strip()

        if not text:
            continue  # skip tool-dispatch AI steps and empty messages

        label = "User" if row["role"] == "human" else "Assistant"
        lines.append(f"**{label}:** {text[:600]}")
        turns += 1

    if len(lines) == 1:
        return ""
    return "\n".join(lines)
