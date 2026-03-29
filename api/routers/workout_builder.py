import json
import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

from api.auth import get_current_user_id
from db.schema import get_connection, set_current_user_id
from agent import workout_builder as workout_builder_agent
from agent.tools.workout_builder import (
    _db_create_training_block,
    _execute_hevy_sync,
    _query_block_performance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workout-builder", tags=["workout-builder"])


# ---------------------------------------------------------------------------
# Streaming chat
# ---------------------------------------------------------------------------

class WorkoutBuilderRequest(BaseModel):
    query: str
    session_id: int | None = None


@router.post("/stream")
async def workout_builder_stream(
    request: WorkoutBuilderRequest,
    user_id: int = Depends(get_current_user_id),
) -> StreamingResponse:
    async def generate():
        try:
            async for event in workout_builder_agent.astream_run(
                request.query,
                request.session_id,
                user_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.exception("Workout builder stream error")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------

@router.get("/programs")
def list_programs(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    """List all training programs for the user (metadata only, no full blocks JSONB)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id::text,
                name,
                type,
                goal_type,
                training_iq_at_generation,
                version,
                is_active,
                hevy_synced_at,
                created_at,
                jsonb_array_length(blocks) AS block_count
            FROM training_programs
            WHERE user_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/programs/{program_id}")
def get_program(
    program_id: str,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Return a single program with its full blocks JSONB."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id::text, name, type, goal_type, training_iq_at_generation, version, "
            "is_active, hevy_synced_at, created_at, blocks "
            "FROM training_programs WHERE id = %s AND user_id = %s",
            (program_id, user_id),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    return dict(row)


@router.post("/programs/{program_id}/sync-to-hevy")
async def sync_program_to_hevy_endpoint(
    program_id: str,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Push a program's routines to Hevy. Only valid for programs with type='hevy'."""
    set_current_user_id(user_id)
    try:
        return _execute_hevy_sync(user_id, program_id)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Training blocks
# ---------------------------------------------------------------------------

class CreateBlockRequest(BaseModel):
    name: str
    goal: str
    start_date: str
    end_date: str | None = None
    notes: str | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"Date must be in YYYY-MM-DD format, got: {v!r}")
        return v


class UpdateBlockRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    end_date: str | None = None
    notes: str | None = None

    @field_validator("end_date", mode="before")
    @classmethod
    def validate_end_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError(f"end_date must be in YYYY-MM-DD format, got: {v!r}")
        return v


@router.get("/blocks")
def list_blocks(user_id: int = Depends(get_current_user_id)) -> list[dict]:
    """List all training blocks for the user, newest first."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                goal,
                start_date,
                end_date,
                notes,
                end_date IS NULL AS is_active,
                created_at
            FROM training_blocks
            WHERE user_id = %s
            ORDER BY start_date DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/blocks")
def create_block(
    body: CreateBlockRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Create a new training block. Closes any currently open block first."""
    start = date.fromisoformat(body.start_date)
    end = date.fromisoformat(body.end_date) if body.end_date else None

    with get_connection() as conn:
        return _db_create_training_block(conn, user_id, body.name, body.goal, start, end, body.notes)


@router.patch("/blocks/{block_id}")
def update_block(
    block_id: int,
    body: UpdateBlockRequest,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Update fields on an existing training block."""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [block_id, user_id]

    with get_connection() as conn:
        row = conn.execute(
            f"UPDATE training_blocks SET {set_clause} WHERE id = %s AND user_id = %s "
            "RETURNING id, name, goal, start_date, end_date, notes, end_date IS NULL AS is_active, created_at",
            values,
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Block not found")
    return dict(row)


@router.get("/blocks/{block_id}/performance")
def get_block_performance_endpoint(
    block_id: int,
    user_id: int = Depends(get_current_user_id),
) -> dict:
    """Return training performance data for a specific block (date-range query)."""
    with get_connection() as conn:
        block = conn.execute(
            "SELECT * FROM training_blocks WHERE id = %s AND user_id = %s",
            (block_id, user_id),
        ).fetchone()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")

        perf = _query_block_performance(conn, user_id, block["start_date"], block["end_date"])

    return {"block": dict(block), **perf}
