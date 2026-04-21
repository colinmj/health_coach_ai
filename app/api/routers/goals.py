from fastapi import APIRouter, Depends, HTTPException, Response

from api.auth import get_current_user_id
from analytics.goals import get_goals_with_actions
from db.schema import get_connection

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("/")
def list_goals(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    return get_goals_with_actions(user_id)


@router.get("/{goal_id}")
def get_goal(goal_id: int, user_id: int = Depends(get_current_user_id)) -> dict:
    goals = get_goals_with_actions(user_id)
    goal = next((g for g in goals if g["id"] == goal_id), None)
    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int, user_id: int = Depends(get_current_user_id)) -> Response:
    with get_connection() as conn:
        goal = conn.execute(
            "SELECT id FROM goals WHERE id = %s AND user_id = %s",
            (goal_id, user_id),
        ).fetchone()
        if not goal:
            raise HTTPException(status_code=404, detail="Goal not found")

        conn.execute(
            "DELETE FROM action_compliance WHERE action_id IN (SELECT id FROM actions WHERE goal_id = %s)",
            (goal_id,),
        )
        conn.execute("DELETE FROM actions WHERE goal_id = %s", (goal_id,))
        conn.execute("DELETE FROM goals WHERE id = %s", (goal_id,))

    return Response(status_code=204)
