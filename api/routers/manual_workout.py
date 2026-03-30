"""API router for manual workout logging.

Endpoints for parsing free-text or photo workout notes via Claude,
saving parsed workouts, listing workouts, and deleting them.
All endpoints require the user's workout_source to be set to 'manual'.
"""

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from api.auth import get_current_user_id
from db.schema import get_connection
from sync.manual_workout import parse_workout_input, save_manual_workout

router = APIRouter(prefix="/manual-workout", tags=["manual-workout"])


def _require_manual_mode(user_id: int) -> None:
    """Raise 403 if the user has not enabled manual workout mode."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT workout_source FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()
    if row is None or row["workout_source"] != "manual":
        raise HTTPException(
            status_code=403,
            detail="Manual workout mode not enabled. Set workout_source to 'manual' in your profile.",
        )


@router.post("/parse")
async def parse_workout(
    text: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Parse free-text or a photo of workout notes into structured JSON.

    Accepts a text field and/or an image file upload (JPEG/PNG).
    Returns {parsed: {...}, warnings: [...]}.
    """
    _require_manual_mode(user_id)

    if not text and file is None:
        raise HTTPException(status_code=400, detail="Provide text, a file, or both.")

    image_bytes: bytes | None = None
    if file is not None:
        image_bytes = await file.read()

    with get_connection() as conn:
        row = conn.execute("SELECT units FROM users WHERE id = %s", (user_id,)).fetchone()
    user_units = row["units"] if row else "metric"

    parsed = parse_workout_input(text=text, image_bytes=image_bytes, user_units=user_units)
    return {"parsed": parsed, "warnings": parsed.get("warnings", [])}


class SaveWorkoutRequest(BaseModel):
    parsed: dict


@router.post("/save")
def save_workout(
    body: SaveWorkoutRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Persist a parsed workout to the database.

    Accepts the parsed dict returned by /parse (or a client-edited version).
    Returns {workout_id: int}.
    """
    _require_manual_mode(user_id)

    with get_connection() as conn:
        workout_id = save_manual_workout(conn, user_id, body.parsed)
        conn.commit()

    return {"workout_id": workout_id}


@router.get("/workouts")
def list_workouts(
    user_id: int = Depends(get_current_user_id),
) -> list[dict]:
    """List all manual workouts for the user, newest first.

    Returns a list of {id, title, start_time, logged_at}.
    """
    _require_manual_mode(user_id)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, start_time, logged_at
            FROM manual_workouts
            WHERE user_id = %s
            ORDER BY COALESCE(start_time, logged_at) DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.get("/workouts/{workout_id}")
def get_workout(
    workout_id: int,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Return a full workout with nested exercises and sets.

    Returns {id, title, notes, start_time, logged_at, exercises: [{...sets: [...]}]}.
    Raises 404 if the workout does not exist or belongs to another user.
    """
    _require_manual_mode(user_id)

    with get_connection() as conn:
        workout_row = conn.execute(
            "SELECT id, title, notes, start_time, logged_at FROM manual_workouts WHERE id = %s AND user_id = %s",
            (workout_id, user_id),
        ).fetchone()

        if workout_row is None:
            raise HTTPException(status_code=404, detail="Workout not found.")

        exercise_rows = conn.execute(
            """
            SELECT id, exercise_template_id, title, notes, exercise_index
            FROM manual_exercises
            WHERE workout_id = %s
            ORDER BY exercise_index
            """,
            (workout_id,),
        ).fetchall()

        exercises = []
        for ex in exercise_rows:
            set_rows = conn.execute(
                """
                SELECT id, set_index, set_type, weight_kg, reps, rpe, estimated_1rm, performance_tag
                FROM manual_sets
                WHERE exercise_id = %s
                ORDER BY set_index
                """,
                (ex["id"],),
            ).fetchall()
            ex_dict = dict(ex)
            ex_dict["sets"] = [dict(s) for s in set_rows]
            exercises.append(ex_dict)

    result = dict(workout_row)
    result["exercises"] = exercises
    return result


@router.delete("/workouts/{workout_id}")
def delete_workout(
    workout_id: int,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Delete a manual workout and all its exercises and sets (CASCADE).

    Raises 404 if the workout does not exist or belongs to another user.
    Returns {deleted: true}.
    """
    _require_manual_mode(user_id)

    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM manual_workouts WHERE id = %s AND user_id = %s",
            (workout_id, user_id),
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Workout not found.")

        conn.execute("DELETE FROM manual_workouts WHERE id = %s", (workout_id,))
        conn.commit()

    return {"deleted": True}
