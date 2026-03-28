import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from api.token_budget import check_budget_dependency
from agent.agent import astream_run

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    query: str
    session_id: int | None = None
    confirmed: bool = False  # True when user has acknowledged re-run of an expensive tool


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    user_id: int = Depends(get_current_user_id),
    _budget: dict = Depends(check_budget_dependency),
) -> StreamingResponse:
    async def generate():
        try:
            async for event in astream_run(
                request.query,
                request.session_id,
                user_id,
                confirmed=request.confirmed,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.exception("Chat stream error")
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
