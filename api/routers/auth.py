import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import get_current_user_id
from db.schema import get_connection

router = APIRouter(prefix="/auth", tags=["auth"])

_log = logging.getLogger(__name__)


def _delete_clerk_user(clerk_user_id: str) -> None:
    secret = os.environ.get("CLERK_SECRET_KEY", "")
    if not secret:
        return
    try:
        httpx.delete(
            f"https://api.clerk.com/v1/users/{clerk_user_id}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10,
        )
    except Exception as e:
        _log.warning("Failed to delete Clerk user %s: %s", clerk_user_id, e)


@router.delete("/account", status_code=204)
def delete_account(user_id: int = Depends(get_current_user_id)) -> None:
    """Permanently delete the authenticated user's account and all their data.

    Removes the local users row (cascading to all data) then deletes the Clerk
    account so the user cannot sign back in with the same identity.
    """
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, clerk_user_id FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
        clerk_user_id = row["clerk_user_id"]
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
    if clerk_user_id:
        _delete_clerk_user(clerk_user_id)
