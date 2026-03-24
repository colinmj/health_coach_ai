from fastapi import APIRouter, Depends, HTTPException

from api.auth import get_current_user_id
from analytics.goals import get_goals_with_protocols_and_actions

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("/")
def list_goals(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    return get_goals_with_protocols_and_actions(user_id)


@router.get("/{goal_id}")
def get_goal(goal_id: int, user_id: int = Depends(get_current_user_id)) -> dict:
    goals = get_goals_with_protocols_and_actions(user_id)
    goal = next((g for g in goals if g["id"] == goal_id), None)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal
