"""Sync Cronometer daily nutrition export (CSV) into PostgreSQL.

Run:
    python -m sync.cronometer path/to/dailysummary.csv

Each run is idempotent — existing rows are updated, new ones inserted.
"""

import csv
import sys
from pathlib import Path

from db.schema import get_connection, get_local_user_id, init_db

# Maps CSV header → DB column name
_COLUMN_MAP = {
    "Date":                      "date",
    "Energy (kcal)":             "energy_kcal",
    "Alcohol (g)":               "alcohol_g",
    "Caffeine (mg)":             "caffeine_mg",
    "Oxalate (mg)":              "oxalate_mg",
    "Phytate (mg)":              "phytate_mg",
    "Water (g)":                 "water_g",
    "B1 (Thiamine) (mg)":        "b1_thiamine_mg",
    "B2 (Riboflavin) (mg)":      "b2_riboflavin_mg",
    "B3 (Niacin) (mg)":          "b3_niacin_mg",
    "B5 (Pantothenic Acid) (mg)":"b5_pantothenic_acid_mg",
    "B6 (Pyridoxine) (mg)":      "b6_pyridoxine_mg",
    "Vitamin C (mg)":            "vitamin_c_mg",
    "Vitamin D (IU)":            "vitamin_d_iu",
    "Vitamin E (mg)":            "vitamin_e_mg",
    "Calcium (mg)":              "calcium_mg",
    "Copper (mg)":               "copper_mg",
    "Iron (mg)":                 "iron_mg",
    "Magnesium (mg)":            "magnesium_mg",
    "Manganese (mg)":            "manganese_mg",
    "Phosphorus (mg)":           "phosphorus_mg",
    "Potassium (mg)":            "potassium_mg",
    "Sodium (mg)":               "sodium_mg",
    "Zinc (mg)":                 "zinc_mg",
    "Net Carbs (g)":             "net_carbs_g",
    "Carbs (g)":                 "carbs_g",
    "Fiber (g)":                 "fiber_g",
    "Insoluble Fiber (g)":       "insoluble_fiber_g",
    "Soluble Fiber (g)":         "soluble_fiber_g",
    "Starch (g)":                "starch_g",
    "Sugars (g)":                "sugars_g",
    "Added Sugars (g)":          "added_sugars_g",
    "Fat (g)":                   "fat_g",
    "Cholesterol (mg)":          "cholesterol_mg",
    "Monounsaturated (g)":       "monounsaturated_g",
    "Polyunsaturated (g)":       "polyunsaturated_g",
    "Saturated (g)":             "saturated_g",
    "Trans-Fats (g)":            "trans_fats_g",
    "ALA (g)":                   "ala_g",
    "DHA (g)":                   "dha_g",
    "EPA (g)":                   "epa_g",
    "AA (g)":                    "aa_g",
    "LA (g)":                    "la_g",
    "Cystine (g)":               "cystine_g",
    "Histidine (g)":             "histidine_g",
    "Isoleucine (g)":            "isoleucine_g",
    "Leucine (g)":               "leucine_g",
    "Lysine (g)":                "lysine_g",
    "Methionine (g)":            "methionine_g",
    "Phenylalanine (g)":         "phenylalanine_g",
    "Protein (g)":               "protein_g",
    "Threonine (g)":             "threonine_g",
    "Tryptophan (g)":            "tryptophan_g",
    "Tyrosine (g)":              "tyrosine_g",
    "Valine (g)":                "valine_g",
    "Completed":                 "completed",
}

# Columns whose CSV header contains µg but may be encoded with garbage bytes
_UG_COLUMNS = {
    "B12 (Cobalamin)": "b12_cobalamin_ug",
    "Folate":          "folate_ug",
    "Vitamin A":       "vitamin_a_ug",
    "Vitamin K":       "vitamin_k_ug",
    "Selenium":        "selenium_ug",
    "Omega-3":         "omega3_g",
    "Omega-6":         "omega6_g",
}


def _resolve_header(raw: str) -> str | None:
    """Return DB column name for a CSV header, handling µg encoding issues."""
    mapped = _COLUMN_MAP.get(raw)
    if mapped:
        return mapped
    # Strip any encoding garbage and try prefix match for µg columns
    clean = raw.encode("ascii", errors="ignore").decode()
    for prefix, col in _UG_COLUMNS.items():
        if clean.startswith(prefix):
            return col
    return None


def _parse_value(col: str, raw: str) -> str | bool | float | None:
    if not raw:
        return None
    if col == "date":
        return raw.strip()
    if col == "completed":
        return raw.strip().upper() == "TRUE"
    try:
        return float(raw)
    except ValueError:
        return None


def sync_csv(csv_path: str | Path) -> None:
    init_db()
    user_id = get_local_user_id()
    csv_path = Path(csv_path)

    if not csv_path.exists():
        print(f"File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    # Build header → db column mapping once from the actual CSV headers
    header_map = {}
    for h in (reader.fieldnames or []):
        col = _resolve_header(h)
        if col:
            header_map[h] = col

    print(f"Importing {len(rows)} rows from {csv_path.name}…")

    with get_connection() as conn:
        for row in rows:
            record: dict = {}
            for csv_header, db_col in header_map.items():
                record[db_col] = _parse_value(db_col, row.get(csv_header, ""))

            if not record.get("date"):
                continue
            record["source"] = "cronometer"
            record["user_id"] = user_id

            cols = list(record.keys())
            placeholders = ", ".join(["%s"] * len(cols))
            updates = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("date", "user_id"))
            sql = (
                f"INSERT INTO nutrition_daily ({', '.join(cols)}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT (user_id, date) DO UPDATE SET {updates}, synced_at=NOW()"
            )
            conn.execute(sql, list(record.values()))
            conn.commit()
            print(f"  ✓ {record['date']}")

    print("Sync complete.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m sync.cronometer <path/to/dailysummary.csv>", file=sys.stderr)
        sys.exit(1)
    sync_csv(sys.argv[1])
