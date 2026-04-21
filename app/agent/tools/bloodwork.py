import json

from langchain_core.tools import tool

from api.feature_gates import Feature, check_tool_feature
from api.tool_confirmation import check_confirmation, fingerprint, record_invocation
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
    if err := check_tool_feature(Feature.BLOODWORK_ANALYSIS):
        return err

    input_hash = fingerprint(f"bloodwork|{since}|{until}|{marker_name}")
    check_confirmation("bloodwork_analysis", input_hash)

    user_id = get_request_user_id()
    with get_connection() as conn:
        rows = _get_biomarkers(
            user_id=user_id,
            conn=conn,
            since=since.strip() or None,
            until=until.strip() or None,
            marker_name=marker_name.strip() or None,
        )
    output = json.dumps(rows, default=str)
    record_invocation("bloodwork_analysis", input_hash, output)
    return output
