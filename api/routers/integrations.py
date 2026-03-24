from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Single source of truth for all supported integrations.
# To add a new source: append one entry here — nothing else changes.
CATALOGUE = [
    {
        "source": "hevy",
        "domain": "strength",
        "load_type": "sync",
        "label": "Hevy",
        "description": "Workouts, sets, 1RM progression",
        "env_key": "HEVY_API_KEY",
    },
    {
        "source": "whoop",
        "domain": "recovery",
        "load_type": "sync",
        "label": "Whoop",
        "description": "HRV, sleep architecture, recovery scores",
        "env_key": "WHOOP_CLIENT_ID",
    },
    {
        "source": "withings",
        "domain": "body_composition",
        "load_type": "sync",
        "label": "Withings",
        "description": "Weight, body fat percentage",
        "env_key": "WITHINGS_CLIENT_ID",
    },
    {
        "source": "cronometer",
        "domain": "nutrition",
        "load_type": "upload",
        "label": "Cronometer",
        "description": "Macros, vitamins, minerals — CSV upload",
        "env_key": None,
    },
]

_SOURCE_META = {e["source"]: e for e in CATALOGUE}


@router.get("/available")
def available_integrations() -> list[dict]:
    """Return the full catalogue of supported sources."""
    return CATALOGUE


class ActivateRequest(BaseModel):
    sources: list[str]
    credentials: dict[str, str] = {}  # source → api key (for non-OAuth integrations)


@router.post("/", status_code=201)
def create_integrations(
    body: ActivateRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Insert user_integrations rows for the selected sources.

    Unknown sources are ignored. Empty list is valid (user skipped onboarding).
    Idempotent — safe to call multiple times.
    """
    if not body.sources:
        return {"created": 0}

    valid = [s for s in body.sources if s in _SOURCE_META]
    with get_connection() as conn:
        for source in valid:
            meta = _SOURCE_META[source]
            api_key = body.credentials.get(source)
            conn.execute(
                """
                INSERT INTO user_integrations (user_id, domain, source, load_type, access_token)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id, domain) DO UPDATE SET
                    source       = EXCLUDED.source,
                    load_type    = EXCLUDED.load_type,
                    access_token = COALESCE(EXCLUDED.access_token, user_integrations.access_token)
                """,
                (user_id, meta["domain"], source, meta["load_type"], api_key),
            )
        conn.commit()

    return {"created": len(valid)}
