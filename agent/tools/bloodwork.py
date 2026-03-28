import json

from langchain_core.tools import tool

from db.schema import get_connection, get_request_user_id
from sync.bloodwork import get_biomarkers as _get_biomarkers


@tool
def get_biomarkers(since: str = "", until: str = "", marker_name: str = "") -> str:
    """Use for questions about blood test results, lab values, or biomarkers.
    Returns biomarker history for markers like testosterone, vitamin_d, ferritin, tsh,
    hemoglobin, glucose, hba1c, cortisol, crp, cholesterol, ldl, hdl, triglycerides, etc.
    since/until are optional YYYY-MM-DD date strings.
    marker_name is optional — omit to return all markers, or pass e.g. "vitamin_d" to filter.
    Returns a JSON list with fields: test_date, marker_name, value, unit,
    reference_low, reference_high, status (low/normal/high).
    IMPORTANT: Always recommend consulting a doctor for clinical interpretation."""
    user_id = get_request_user_id()
    with get_connection() as conn:
        rows = _get_biomarkers(
            user_id=user_id,
            conn=conn,
            since=since.strip() or None,
            until=until.strip() or None,
            marker_name=marker_name.strip() or None,
        )
    return json.dumps(rows, default=str)
