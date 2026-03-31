import io
import zipfile

import anthropic
from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile

from api.auth import get_current_user_id
from db.schema import get_connection
from sync.utils import needs_sync
from sync.hevy import sync_workouts
from sync.whoop import sync_whoop
from sync.withings import sync_withings
from sync.oura import sync_oura
from sync.cronometer import auto_sync_csv
from sync.strong import sync_strong_csv
from sync.apple_health import sync_apple_health_xml
from sync.bloodwork import extract_biomarkers, upsert_biomarkers
from sync.form_analysis import SUPPORTED_EXERCISES, analyze_video, save_form_analysis

router = APIRouter(prefix="/sync", tags=["sync"])


def _run_pending_syncs(user_id: int) -> None:
    from db.schema import set_current_user_id
    set_current_user_id(user_id)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT source FROM user_integrations
            WHERE user_id = %s AND auth_type IN ('oauth', 'api_key') AND is_active = TRUE
            """,
            (user_id,),
        ).fetchall()

    connected = {row["source"] for row in rows}

    _SYNC_HANDLERS = {
        "hevy":     sync_workouts,
        "whoop":    sync_whoop,
        "withings": sync_withings,
        "oura":     sync_oura,
    }

    for source, handler in _SYNC_HANDLERS.items():
        if source in connected and needs_sync(user_id, source):
            try:
                handler()
            except Exception as e:
                print(f"[sync] {source} failed: {e}")


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
    """Accept a Cronometer CSV (Daily Summary or Servings format).

    Auto-detects the format from the first column header:
    - "Date" → Daily Summary → upserts into nutrition_daily
    - "Day"  → Servings     → upserts into nutrition_foods
    """
    content = await file.read()
    try:
        with get_connection() as conn:
            result = auto_sync_csv(content, user_id, conn)
            conn.execute(
                "UPDATE user_integrations SET last_synced_at=NOW() WHERE user_id=%s AND source='cronometer'",
                (user_id,),
            )
            conn.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.post("/upload-strong")
async def upload_strong(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Accept a Strong workout CSV export, upsert into strong_workouts / exercises / sets."""
    content = await file.read()
    try:
        with get_connection() as conn:
            count = sync_strong_csv(content, user_id, conn)
            conn.execute(
                "UPDATE user_integrations SET last_synced_at=NOW() WHERE user_id=%s AND source='strong'",
                (user_id,),
            )
            conn.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"workouts_imported": count}


@router.post("/upload-apple-health")
async def upload_apple_health(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Accept an Apple Health export ZIP or raw export.xml, upsert sleep/recovery/body/cardio data."""
    content = await file.read()
    if content[:2] == b'PK':  # ZIP magic bytes
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                xml_name = next(
                    (n for n in zf.namelist() if n.endswith('export.xml')), None
                )
                if xml_name is None:
                    raise HTTPException(status_code=422, detail="No export.xml found in ZIP")
                with zf.open(xml_name) as xml_file:
                    content = xml_file.read()
        except zipfile.BadZipFile:
            raise HTTPException(status_code=422, detail="Invalid ZIP file")
    try:
        with get_connection() as conn:
            counts = sync_apple_health_xml(content, user_id, conn)
            conn.execute(
                "UPDATE user_integrations SET last_synced_at=NOW() WHERE user_id=%s AND source='apple_health'",
                (user_id,),
            )
            conn.commit()
    except (ValueError, Exception) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"rows_imported": counts}


@router.post("/upload-bloodwork")
async def upload_bloodwork(
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Accept a bloodwork PDF or image, extract biomarkers via Claude, and upsert into the database."""
    content = await file.read()
    content_type = file.content_type or "application/pdf"
    try:
        rows = extract_biomarkers(content, content_type)
        with get_connection() as conn:
            count = upsert_biomarkers(rows, user_id, conn)
            conn.execute(
                "UPDATE user_integrations SET last_synced_at=NOW() WHERE user_id=%s AND source='bloodwork'",
                (user_id,),
            )
            conn.commit()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"biomarkers_imported": count}


@router.post("/upload-video")
async def upload_video(
    exercise_name: str = Form(...),
    file: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Accept a lifting video (MP4 or MOV), extract frames, analyse form via Claude vision,
    and persist the result in form_analyses."""
    if exercise_name not in SUPPORTED_EXERCISES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exercise '{exercise_name}'. "
                   f"Supported: {', '.join(sorted(SUPPORTED_EXERCISES))}",
        )
    content = await file.read()
    try:
        with get_connection() as conn:
            result = analyze_video(content, exercise_name, conn)
            save_form_analysis(result, user_id, exercise_name, conn)
            conn.commit()
    except anthropic._exceptions.OverloadedError:
        raise HTTPException(
            status_code=503,
            detail="The AI service is temporarily overloaded. Please try again in a moment.",
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return result


@router.get("/form-analyses")
def list_form_analyses(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    """Return the 20 most recent form analyses for the current user."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, exercise_name, video_date, frame_count, overall_rating,
                   findings, cues, recovery_score_day_of, created_at
            FROM form_analyses
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/status")
def sync_status(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    from api.routers.integrations import _SOURCE_META
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT source, auth_type, last_synced_at, is_active,
                   (access_token IS NOT NULL) AS authorized
            FROM user_integrations
            WHERE user_id = %s
            ORDER BY source
            """,
            (user_id,),
        ).fetchall()

    result = []
    for row in rows:
        meta = _SOURCE_META.get(row["source"], {})
        result.append({
            **dict(row),
            "data_types": meta.get("data_types", []),
            "label": meta.get("label", row["source"]),
        })
    return result
