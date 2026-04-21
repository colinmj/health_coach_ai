from fastapi import APIRouter, Depends

from api.auth import get_current_user_id
from analytics.goals import get_active_insights

router = APIRouter(prefix="/insights", tags=["insights"])


@router.get("/")
def list_insights(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    return get_active_insights(user_id)
