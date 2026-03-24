from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile

from api.auth import get_current_user_id
from db.schema import get_connection
from sync.utils import needs_sync
from sync.hevy import sync_workouts
from sync.whoop import sync_whoop
from sync.withings import sync_withings
from sync.cronometer import sync_csv_content

router = APIRouter(prefix="/sync", tags=["sync"])


def _run_pending_syncs(user_id: int) -> None:
    """Run syncs for any source that is past the throttle window."""
    from db.schema import set_current_user_id
    set_current_user_id(user_id)

    if needs_sync(user_id, "strength"):
        try:
            sync_workouts()
        except Exception as e:
            print(f"[sync] strength failed: {e}")

    if needs_sync(user_id, "recovery"):
        try:
            sync_whoop()
        except Exception as e:
            print(f"[sync] recovery failed: {e}")

    if needs_sync(user_id, "body_composition"):
        try:
            sync_withings()
        except Exception as e:
            print(f"[sync] body_composition failed: {e}")


@router.post("/trigger")
async def trigger_sync(
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Trigger background syncs for any source past the throttle window.

    Returns immediately — sync runs in the background.
    Cronometer is excluded (manual CSV upload only).
    """
    background_tasks.add_task(_run_pending_syncs, user_id)
    return {"status": "sync started"}


@router.post("/upload-csv")
async def upload_csv(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Accept a Cronometer Daily Summary CSV, upsert into nutrition_daily."""
    content = await file.read()
    try:
        with get_connection() as conn:
            rows = sync_csv_content(content, user_id, conn)
            conn.execute(
                "UPDATE user_integrations SET last_synced_at=NOW() WHERE user_id=%s AND source='cronometer'",
                (user_id,),
            )
            conn.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"rows_imported": rows}


@router.get("/status")
def sync_status(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    """Return last_synced_at for each connected source."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT domain, source, load_type, last_synced_at, is_active,
                   (access_token IS NOT NULL) AS authorized
            FROM user_integrations
            WHERE user_id = %s
            ORDER BY domain
            """,
            (user_id,),
        ).fetchall()
    return list(rows)
