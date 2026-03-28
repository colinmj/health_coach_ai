import json

from langchain_core.tools import tool

from db.schema import get_connection


@tool
def search_health_knowledge(query: str) -> str:
    """Search the health knowledge base (articles, research guides) for information
    about biomarker interpretation, lab reference ranges, and clinical guidelines.

    Use this when the user asks general questions about interpreting blood lab results
    or health markers — e.g. what a TSH value means, what an elevated HbA1c indicates,
    how to read a cholesterol panel, or what normal reference ranges are.

    Do NOT use this for the user's own biomarker values — use get_biomarkers for that.
    This searches reference literature, not personal data.
    """
    query = query.strip()
    if not query:
        return "No query provided."
    sql = """
        SELECT document_name, source_url, content
        FROM document_chunks
        WHERE tsv @@ plainto_tsquery('english', %s)
        ORDER BY ts_rank(tsv, plainto_tsquery('english', %s)) DESC
        LIMIT 5
    """
    with get_connection() as conn:
        rows = conn.execute(sql, (query, query)).fetchall()
    if not rows:
        return "No relevant information found in the knowledge base."
    return json.dumps([dict(r) for r in rows])
