import base64
import json
import os

import anthropic

from db.schema import get_connection
from services.encryption import decrypt, encrypt

EXTRACTION_PROMPT = """You are extracting structured biomarker data from a lab report.

Return ONLY a valid JSON array. No prose, no explanation, no markdown fences.

Each object must have:
  "test_date": "YYYY-MM-DD" (specimen/collection date from the report — look for "Collection Date", "Specimen Date", "Date Collected", etc.),
  "marker_name": canonical snake_case name,
  "value": numeric value (number, not string),
  "unit": unit of measurement (e.g. "ng/mL", "pg/mL", "g/dL", "IU/L"),
  "reference_low": lower bound of lab reference range (number or null),
  "reference_high": upper bound of lab reference range (number or null)

Normalize marker names to canonical snake_case:
- "25-OH Vitamin D" / "25(OH)D" / "Vitamin D, 25-Hydroxy" / "25-Hydroxyvitamin D" → "vitamin_d"
- "T. Testosterone" / "Testosterone, Total" / "Total Testosterone" → "testosterone"
- "Free T4" / "Thyroxine, Free" / "T4, Free" → "free_t4"
- "Free T3" / "Triiodothyronine, Free" → "free_t3"
- "TSH" / "Thyroid Stimulating Hormone" / "Thyrotropin" → "tsh"
- "Hgb" / "Hemoglobin" → "hemoglobin"
- "Hct" / "Hematocrit" → "hematocrit"
- "WBC" / "White Blood Cell Count" → "wbc"
- "RBC" / "Red Blood Cell Count" → "rbc"
- "MCV" → "mcv"
- "MCH" → "mch"
- "MCHC" → "mchc"
- "Ferritin" / "Serum Ferritin" → "ferritin"
- "Iron" / "Serum Iron" → "iron"
- "TIBC" / "Total Iron Binding Capacity" → "tibc"
- "Glucose" / "Fasting Glucose" → "glucose"
- "HbA1c" / "Hemoglobin A1c" / "Glycated Hemoglobin" → "hba1c"
- "Cortisol" / "Serum Cortisol" → "cortisol"
- "DHEA-S" / "DHEA Sulfate" → "dhea_s"
- "LH" / "Luteinizing Hormone" → "lh"
- "FSH" / "Follicle Stimulating Hormone" → "fsh"
- "Estradiol" / "E2" → "estradiol"
- "IGF-1" / "Insulin-like Growth Factor 1" → "igf_1"
- "CRP" / "C-Reactive Protein" / "hsCRP" → "crp"
- "Homocysteine" → "homocysteine"
- "Cholesterol" / "Total Cholesterol" → "total_cholesterol"
- "LDL" / "LDL Cholesterol" → "ldl"
- "HDL" / "HDL Cholesterol" → "hdl"
- "Triglycerides" → "triglycerides"
- "ALT" / "Alanine Aminotransferase" → "alt"
- "AST" / "Aspartate Aminotransferase" → "ast"
- "GGT" / "Gamma-Glutamyl Transferase" → "ggt"
- "Creatinine" → "creatinine"
- "eGFR" / "Estimated GFR" → "egfr"
- "Uric Acid" → "uric_acid"
- "Sodium" → "sodium"
- "Potassium" → "potassium"
- "Magnesium" → "magnesium"
- "Calcium" → "calcium"
- "Phosphorus" → "phosphorus"
- "Zinc" → "zinc"
- "Vitamin B12" / "Cobalamin" → "vitamin_b12"
- "Folate" / "Folic Acid" → "folate"
- "PSA" / "Prostate Specific Antigen" → "psa"
- For any other marker: convert to lowercase snake_case

If the test date cannot be found, use null for test_date.
Skip any row where value is not a number (e.g. "See note", "Pending", ">", "<", or text-only results).
Skip rows that are clearly headers, footnotes, or non-result lines."""


def _compute_status(
    value: float,
    reference_low: float | None,
    reference_high: float | None,
) -> str:
    if reference_low is not None and value < reference_low:
        return "low"
    if reference_high is not None and value > reference_high:
        return "high"
    return "normal"


def extract_biomarkers(file_bytes: bytes, content_type: str) -> list[dict]:
    """Send the file to Claude and extract biomarker data as a list of dicts."""
    b64 = base64.standard_b64encode(file_bytes).decode()

    if content_type == "application/pdf":
        file_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": b64,
            },
        }
        betas = ["pdfs-2024-09-25"]
    else:
        file_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": content_type,
                "data": b64,
            },
        }
        betas = []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    kwargs: dict = {
        "model": "claude-opus-4-6",
        "max_tokens": 4096,
        "messages": [
            {
                "role": "user",
                "content": [
                    file_block,
                    {"type": "text", "text": EXTRACTION_PROMPT},
                ],
            }
        ],
    }
    if betas:
        kwargs["betas"] = betas

    response = client.beta.messages.create(**kwargs) if betas else client.messages.create(**kwargs)

    raw = response.content[0].text.strip()
    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Claude returned non-JSON response: {e}\n\nResponse was:\n{raw[:500]}") from e

    if not isinstance(rows, list):
        raise ValueError(f"Expected JSON array, got {type(rows).__name__}")

    return rows


def upsert_biomarkers(rows: list[dict], user_id: int, conn) -> int:
    """Encrypt and upsert biomarker rows. Returns count of rows upserted."""
    count = 0
    for row in rows:
        try:
            value_raw = row.get("value")
            ref_low_raw = row.get("reference_low")
            ref_high_raw = row.get("reference_high")
            test_date = row.get("test_date")
            marker_name = row.get("marker_name", "").strip()

            if not marker_name:
                continue
            if value_raw is None:
                continue
            value_float = float(value_raw)

            ref_low = float(ref_low_raw) if ref_low_raw is not None else None
            ref_high = float(ref_high_raw) if ref_high_raw is not None else None

            status = _compute_status(value_float, ref_low, ref_high)

            conn.execute(
                """
                INSERT INTO biomarkers
                    (user_id, test_date, marker_name, value, unit, reference_low,
                     reference_high, status, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pdf_upload')
                ON CONFLICT (user_id, test_date, marker_name) DO UPDATE SET
                    value         = EXCLUDED.value,
                    unit          = EXCLUDED.unit,
                    reference_low = EXCLUDED.reference_low,
                    reference_high= EXCLUDED.reference_high,
                    status        = EXCLUDED.status,
                    synced_at     = NOW()
                """,
                [
                    user_id,
                    test_date,
                    marker_name,
                    encrypt(value_float),
                    encrypt(row.get("unit")),
                    encrypt(ref_low),
                    encrypt(ref_high),
                    encrypt(status),
                ],
            )
            count += 1
        except (TypeError, ValueError):
            continue

    return count


def get_biomarkers(
    user_id: int,
    conn,
    since: str | None = None,
    until: str | None = None,
    marker_name: str | None = None,
) -> list[dict]:
    """Fetch and decrypt biomarkers for a user."""
    conditions = ["user_id = %s"]
    params: list = [user_id]

    if since:
        conditions.append("test_date >= %s")
        params.append(since)
    if until:
        conditions.append("test_date <= %s")
        params.append(until)
    if marker_name:
        conditions.append("marker_name = %s")
        params.append(marker_name.strip())

    where = "WHERE " + " AND ".join(conditions)
    sql = f"""
        SELECT test_date, marker_name, value, unit, reference_low, reference_high, status
        FROM biomarkers
        {where}
        ORDER BY test_date, marker_name
    """
    rows = conn.execute(sql, params).fetchall()

    result = []
    for row in rows:
        d = dict(row)
        raw_value = decrypt(d["value"])
        raw_low = decrypt(d["reference_low"])
        raw_high = decrypt(d["reference_high"])
        result.append({
            "test_date": str(d["test_date"]),
            "marker_name": d["marker_name"],
            "value": float(raw_value) if raw_value is not None else None,
            "unit": decrypt(d["unit"]),
            "reference_low": float(raw_low) if raw_low is not None else None,
            "reference_high": float(raw_high) if raw_high is not None else None,
            "status": decrypt(d["status"]),
        })
    return result
