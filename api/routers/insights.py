from fastapi import APIRouter

from db.schema import get_local_user_id
from analytics.goals import get_active_insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/")
def list_insights() -> list[dict]:
    user_id = get_local_user_id()
    return get_active_insights(user_id)
