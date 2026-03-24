from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/")
def get_profile(user_id: int = Depends(get_current_user_id)) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT email, name, date_of_birth, sex, height_cm, units FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


class ProfileUpdate(BaseModel):
    name: str | None = None
    date_of_birth: str | None = None
    sex: str | None = None
    height_cm: float | None = None
    units: str | None = None


@router.patch("/")
def update_profile(
    body: ProfileUpdate,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        return {"updated": False}

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [user_id]

    with get_connection() as conn:
        conn.execute(
            f"UPDATE users SET {set_clause}, updated_at = NOW() WHERE id = %s",  # noqa: S608
            values,
        )
        conn.commit()
    return {"updated": True}
