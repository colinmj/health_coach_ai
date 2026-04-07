from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/integrations", tags=["integrations"])

CATALOGUE = [
    {
        "source":      "hevy",
        "label":       "Hevy",
        "description": "Workouts, sets, 1RM progression",
        "auth_type":   "api_key",
        "data_types":  ["strength_workouts"],
        "env_key":     "HEVY_API_KEY",
    },
    {
        "source":      "strong",
        "label":       "Strong",
        "description": "Strength workout history — CSV export",
        "auth_type":   "upload",
        "data_types":  ["strength_workouts"],
        "env_key":     None,
    },
    {
        "source":      "whoop",
        "label":       "Whoop",
        "description": "HRV, sleep architecture, recovery scores, cardio",
        "auth_type":   "oauth",
        "data_types":  ["sleep", "hrv_recovery", "activities"],
        "env_key":     "WHOOP_CLIENT_ID",
    },
    {
        "source":      "oura",
        "label":       "Oura",
        "description": "Sleep, HRV, readiness score",
        "auth_type":   "oauth",
        "data_types":  ["sleep", "hrv_recovery"],
        "env_key":     "OURA_CLIENT_ID",
    },
    {
        "source":      "apple_health",
        "label":       "Apple Health",
        "description": "All domains — export from the Health app",
        "auth_type":   "upload",
        "data_types":  ["sleep", "hrv_recovery", "strength_workouts", "activities", "body_composition", "nutrition"],
        "env_key":     None,
    },
    {
        "source":      "withings",
        "label":       "Withings",
        "description": "Weight, body fat percentage",
        "auth_type":   "oauth",
        "data_types":  ["body_composition"],
        "env_key":     "WITHINGS_CLIENT_ID",
    },
    {
        "source":      "cronometer",
        "label":       "Cronometer",
        "description": "Macros, vitamins, minerals — CSV upload",
        "auth_type":   "upload",
        "data_types":  ["nutrition"],
        "env_key":     None,
    },
    {
        "source":      "bloodwork",
        "label":       "Bloodwork",
        "description": "Lab results — PDF or photo upload",
        "auth_type":   "upload",
        "data_types":  ["bloodwork"],
        "env_key":     None,
    },
]

DATA_TYPE_LABELS = {
    "sleep":             "Sleep",
    "hrv_recovery":      "HRV & Recovery",
    "strength_workouts": "Strength Training",
    "activities":   "Cardio",
    "body_composition":  "Body Composition",
    "nutrition":         "Nutrition",
}

_SOURCE_META = {e["source"]: e for e in CATALOGUE}


def _update_workout_source(conn, user_id: int) -> None:
    """Recompute and persist workout_source from active workout integrations."""
    row = conn.execute(
        """
        SELECT source FROM user_integrations
        WHERE user_id = %s AND source IN ('hevy', 'strong') AND is_active = TRUE
        ORDER BY CASE source WHEN 'hevy' THEN 1 WHEN 'strong' THEN 2 END
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    source = row["source"] if row else "manual"
    conn.execute("UPDATE users SET workout_source = %s WHERE id = %s", (source, user_id))


@router.get("/available")
def available_integrations() -> list[dict]:
    return CATALOGUE


class ActivateRequest(BaseModel):
    sources: list[str]
    credentials: dict[str, str] = {}


@router.post("/", status_code=201)
def create_integrations(
    body: ActivateRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    valid = [s for s in body.sources if s in _SOURCE_META]
    if not valid:
        return {"created": 0}

    with get_connection() as conn:
        for source in valid:
            meta = _SOURCE_META[source]
            api_key = body.credentials.get(source)
            conn.execute(
                """
                INSERT INTO user_integrations (user_id, source, auth_type, access_token)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, source) DO UPDATE SET
                    auth_type    = EXCLUDED.auth_type,
                    access_token = COALESCE(EXCLUDED.access_token, user_integrations.access_token)
                """,
                (user_id, source, meta["auth_type"], api_key),
            )
        _update_workout_source(conn, user_id)
        conn.commit()

    return {"created": len(valid)}


class DataImportRequest(BaseModel):
    assignments: dict[str, str]


@router.post("/data-imports", status_code=201)
def save_data_imports(
    body: DataImportRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    if not body.assignments:
        return {"saved": 0}

    with get_connection() as conn:
        for data_type, source in body.assignments.items():
            conn.execute(
                """
                INSERT INTO user_data_imports (user_id, data_type, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, data_type) DO UPDATE SET
                    source     = EXCLUDED.source,
                    updated_at = NOW()
                """,
                (user_id, data_type, source),
            )
        conn.commit()

    return {"saved": len(body.assignments)}


@router.get("/data-imports")
def get_data_imports(user_id: int = Depends(get_current_user_id)) -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT data_type, source FROM user_data_imports WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return {row["data_type"]: row["source"] for row in rows}


@router.delete("/{source}", status_code=204)
def delete_integration(
    source: str,
    user_id: int = Depends(get_current_user_id),
) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM user_integrations WHERE user_id = %s AND source = %s",
            (user_id, source),
        )
        conn.execute(
            "DELETE FROM user_data_imports WHERE user_id = %s AND source = %s",
            (user_id, source),
        )
        _update_workout_source(conn, user_id)
        conn.commit()
