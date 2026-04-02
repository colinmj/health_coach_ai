import json

from langchain_core.tools import tool

from db.schema import get_connection


@tool
def search_health_knowledge(query: str) -> str:
    """Search the health and training knowledge base before answering ANY question about:
    - Training methodology, programming, or periodization (e.g. 5/3/1, RPE, conjugate,
      progressive overload, deload, training max — search "5/3/1" not "531")
    - Biomarker interpretation, lab reference ranges, or clinical guidelines
    - Strength, hypertrophy, or conditioning concepts

    ALWAYS call this tool first when the user asks a training or health knowledge question.
    The knowledge base contains the user's uploaded books and articles — answers from here
    are more relevant than general knowledge. Only fall back to general knowledge if this
    tool returns no results.

    Do NOT use this for the user's own personal data — use the appropriate data tools for that.
    """
    query = query.strip()
    if not query:
        return "No query provided."
    sql = """
        SELECT document_name, source_url, content
        FROM document_chunks
        WHERE tsv @@ plainto_tsquery('simple', %s)
        ORDER BY ts_rank(tsv, plainto_tsquery('simple', %s)) DESC
        LIMIT 5
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (query, query)).fetchall()
    if not rows:
        return "No relevant information found in the knowledge base."
    return json.dumps([dict(r) for r in rows])
