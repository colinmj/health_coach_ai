import io
import os
from datetime import datetime, timezone
from uuid import uuid4

import pillow_heif
from PIL import Image
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from api.auth import get_current_user_id
from clients.r2 import get_r2_client
from db.schema import get_connection

pillow_heif.register_heif_opener()

router = APIRouter(prefix="/progress-photos", tags=["progress-photos"])

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}
MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/heic": "heic",
}


@router.post("/")
async def upload_progress_photo(
    file: UploadFile = File(...),
    taken_at: str | None = Form(None),
    notes: str | None = Form(None),
    user_id: int = Depends(get_current_user_id),
):
    content_type = file.content_type or ""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{content_type}'. Upload a JPEG, PNG, WebP, or HEIC image.",
        )

    if taken_at:
        try:
            taken_dt = datetime.fromisoformat(taken_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid taken_at format. Use ISO 8601.")
    else:
        taken_dt = datetime.now(timezone.utc)

    data = await file.read()

    if content_type == "image/heic":
        img = Image.open(io.BytesIO(data))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
        content_type = "image/jpeg"

    ext = MIME_TO_EXT[content_type]
    r2_key = f"{user_id}/{uuid4()}.{ext}"

    bucket = os.environ["R2_BUCKET_NAME"]
    r2 = get_r2_client()
    r2.put_object(
        Bucket=bucket,
        Key=r2_key,
        Body=data,
        ContentType=content_type,
    )

    with get_connection() as conn:
        row = conn.execute(
            """
            INSERT INTO progress_photos (user_id, r2_key, taken_at, notes)
            VALUES (%s, %s, %s, %s)
            RETURNING id, taken_at
            """,
            (user_id, r2_key, taken_dt, notes),
        ).fetchone()
    
    return {"photo_id": row["id"], "taken_at": row["taken_at"]}


@router.delete("/{photo_id}", status_code=204)
def delete_progress_photo(photo_id: int, user_id: int = Depends(get_current_user_id)):
    with get_connection() as conn:
        row = conn.execute(
            "DELETE FROM progress_photos WHERE id = %s AND user_id = %s RETURNING r2_key",
            (photo_id, user_id),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Photo not found")

    bucket = os.environ["R2_BUCKET_NAME"]
    get_r2_client().delete_object(Bucket=bucket, Key=row["r2_key"])


PRESIGNED_URL_TTL = 900  # 15 minutes
PAGE_LIMIT = 10


@router.get("/")
def list_progress_photos(
    user_id: int = Depends(get_current_user_id),
    page: int = Query(1, ge=1),
):
    offset = (page - 1) * PAGE_LIMIT

    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM progress_photos WHERE user_id = %s",
            (user_id,),
        ).fetchone()["count"]

        rows = conn.execute(
            """
            SELECT id, r2_key, taken_at, notes, created_at
            FROM progress_photos
            WHERE user_id = %s
            ORDER BY taken_at DESC
            LIMIT %s OFFSET %s
            """,
            (user_id, PAGE_LIMIT, offset),
        ).fetchall()

    bucket = os.environ["R2_BUCKET_NAME"]
    r2 = get_r2_client()

    return {
        "total": total,
        "page": page,
        "page_size": PAGE_LIMIT,
        "photos": [
            {
                "id": r["id"],
                "url": r2.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": r["r2_key"]},
                    ExpiresIn=PRESIGNED_URL_TTL,
                ),
                "taken_at": r["taken_at"],
                "notes": r["notes"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }
