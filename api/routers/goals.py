from fastapi import APIRouter, HTTPException

from db.schema import get_local_user_id
from analytics.goals import get_goals_with_protocols_and_actions

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("/")
def list_goals() -> list[dict]:
    user_id = get_local_user_id()
    return get_goals_with_protocols_and_actions(user_id)


@router.get("/{goal_id}")
def get_goal(goal_id: int) -> dict:
    user_id = get_local_user_id()
    goals = get_goals_with_protocols_and_actions(user_id)
    goal = next((g for g in goals if g["id"] == goal_id), None)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal
