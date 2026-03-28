"""Sync Cronometer daily nutrition export (CSV) into PostgreSQL.

Run:
    python -m sync.cronometer path/to/dailysummary.csv

Each run is idempotent — existing rows are updated, new ones inserted.
"""

import csv
import io
import os
import sys
from pathlib import Path

from db.schema import get_connection, get_request_user_id, set_current_user_id, get_cli_user_id, init_db

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
    "B5 (Pantothenic Acid) (mg)": "b5_pantothenic_acid_mg",
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


def sync_csv_content(content: bytes, user_id: int, conn) -> int:
    """Parse raw CSV bytes and upsert into nutrition_daily. Returns row count.

    Raises ValueError if the file doesn't look like a Cronometer Daily Summary CSV.
    """
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)

    # Build header → db column mapping
    header_map = {}
    for h in (reader.fieldnames or []):
        col = _resolve_header(h)
        if col:
            header_map[h] = col

    # Validate: must have Date + at least 3 other recognised columns
    db_cols = set(header_map.values())
    if "date" not in db_cols:
        raise ValueError(
            'Missing required "Date" column. Please upload a Cronometer Daily Summary CSV.'
        )
    if len(db_cols) < 4:
        raise ValueError(
            "This doesn't look like a Cronometer Daily Summary CSV — too few recognised columns."
        )

    count = 0
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
        count += 1

    conn.commit()
    return count


# Maps the Servings CSV's extra columns → DB column names.
# Nutrient columns are resolved via the shared _COLUMN_MAP / _UG_COLUMNS above.
_FOOD_COLUMN_MAP = {
    "Day":       "date",
    "Time":      "logged_at",
    "Group":     "meal_group",
    "Food Name": "food_name",
    "Amount":    "amount",
    "Category":  "category",
}

# Hardcoded ordered list of every nutrient column in nutrition_foods.
# Used to build the INSERT column list safely (no dynamic user-controlled keys).
_FOOD_NUTRIENT_COLUMNS = [
    "energy_kcal", "alcohol_g", "caffeine_mg", "oxalate_mg", "phytate_mg",
    "water_g", "b1_thiamine_mg", "b2_riboflavin_mg", "b3_niacin_mg",
    "b5_pantothenic_acid_mg", "b6_pyridoxine_mg", "b12_cobalamin_ug",
    "folate_ug", "vitamin_a_ug", "vitamin_c_mg", "vitamin_d_iu", "vitamin_e_mg",
    "vitamin_k_ug", "calcium_mg", "copper_mg", "iron_mg", "magnesium_mg",
    "manganese_mg", "phosphorus_mg", "potassium_mg", "selenium_ug", "sodium_mg",
    "zinc_mg", "net_carbs_g", "carbs_g", "fiber_g", "insoluble_fiber_g",
    "soluble_fiber_g", "starch_g", "sugars_g", "added_sugars_g", "fat_g",
    "cholesterol_mg", "monounsaturated_g", "polyunsaturated_g", "saturated_g",
    "trans_fats_g", "omega3_g", "omega6_g", "ala_g", "dha_g", "epa_g", "aa_g",
    "la_g", "cystine_g", "histidine_g", "isoleucine_g", "leucine_g", "lysine_g",
    "methionine_g", "phenylalanine_g", "protein_g", "threonine_g",
    "tryptophan_g", "tyrosine_g", "valine_g",
]

_FOOD_ALL_COLUMNS = (
    ["user_id", "date", "logged_at", "meal_group", "food_name", "amount", "category"]
    + _FOOD_NUTRIENT_COLUMNS
)


def sync_food_csv_content(content: bytes, user_id: int, conn) -> dict:
    """Parse raw Cronometer Servings CSV bytes and insert into nutrition_foods.

    Idempotency: deletes all existing rows for each date present in the CSV,
    then bulk-inserts the new rows.

    Returns {"inserted": N, "days": M}.
    Raises ValueError if the file doesn't look like a Cronometer Servings CSV.
    """
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    raw_rows = list(reader)

    # Build a header → db_column map for every column in this file
    header_map: dict[str, str] = {}
    for h in (reader.fieldnames or []):
        # Check food-specific columns first, then fall back to nutrient resolver
        col = _FOOD_COLUMN_MAP.get(h) or _resolve_header(h)
        if col and col != "completed":  # 'completed' is daily-only
            header_map[h] = col

    db_cols = set(header_map.values())
    if "food_name" not in db_cols:
        raise ValueError(
            'Missing required "Food Name" column. Please upload a Cronometer Servings CSV.'
        )
    if "date" not in db_cols:
        raise ValueError(
            'Missing required "Day" column. Please upload a Cronometer Servings CSV.'
        )

    records: list[dict] = []
    unique_dates: set[str] = set()

    for row in raw_rows:
        record: dict = {}
        for csv_header, db_col in header_map.items():
            raw = row.get(csv_header, "")
            if not raw:
                record[db_col] = None
            elif db_col == "date":
                record[db_col] = raw.strip()
            elif db_col in ("logged_at", "meal_group", "food_name", "amount", "category"):
                record[db_col] = raw.strip()
            else:
                try:
                    record[db_col] = float(raw)
                except ValueError:
                    record[db_col] = None

        date_val = record.get("date")
        if not date_val or not record.get("food_name"):
            continue

        unique_dates.add(date_val)
        records.append(record)

    if not records:
        return {"inserted": 0, "days": 0}

    # Delete existing rows for the affected date range, then bulk-insert
    conn.execute(
        "DELETE FROM nutrition_foods WHERE user_id = %s AND date = ANY(%s)",
        (user_id, list(unique_dates)),
    )

    placeholders = ", ".join(["%s"] * len(_FOOD_ALL_COLUMNS))
    insert_sql = (
        f"INSERT INTO nutrition_foods ({', '.join(_FOOD_ALL_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )

    for record in records:
        values = [user_id if col == "user_id" else record.get(col) for col in _FOOD_ALL_COLUMNS]
        conn.execute(insert_sql, values)

    conn.commit()
    return {"inserted": len(records), "days": len(unique_dates)}


def auto_sync_csv(content: bytes, user_id: int, conn) -> dict:
    """Detect Cronometer CSV format and dispatch to the correct sync function.

    - First header == "Day"  → Servings / food-item format → nutrition_foods
    - First header == "Date" → Daily Summary format        → nutrition_daily

    Returns a unified dict; callers should check which keys are present.
    Raises ValueError for unrecognised formats.
    """
    text = content.decode("utf-8-sig")
    # Peek at the first header without re-reading the whole file
    first_line = text.split("\n", 1)[0]
    first_header = next(csv.reader([first_line]), [""])[0].strip()

    if first_header == "Day":
        result = sync_food_csv_content(content, user_id, conn)
        return result
    elif first_header == "Date":
        rows = sync_csv_content(content, user_id, conn)
        return {"rows_imported": rows}
    else:
        raise ValueError(
            f'Unrecognised Cronometer CSV format (first column: "{first_header}"). '
            "Please upload a Daily Summary or Servings export."
        )


def sync_csv(csv_path: str | Path) -> None:
    init_db()
    user_id = get_request_user_id()
    csv_path = Path(csv_path)

    if not csv_path.exists():
        print(f"File not found: {csv_path}", file=sys.stderr)
        sys.exit(1)

    content = csv_path.read_bytes()
    print(f"Importing from {csv_path.name}…")

    with get_connection() as conn:
        count = sync_csv_content(content, user_id, conn)

    print(f"Sync complete. {count} rows imported.")


if __name__ == "__main__":
    set_current_user_id(get_cli_user_id())
    if len(sys.argv) != 2:
        print("Usage: python -m sync.cronometer <path/to/dailysummary.csv>", file=sys.stderr)
        sys.exit(1)
    sync_csv(sys.argv[1])
