import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth import get_current_user_id
from agent.agent import astream_run

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    query: str
    session_id: int | None = None


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    _user_id: int = Depends(get_current_user_id),
) -> StreamingResponse:
    async def generate():
        try:
            async for event in astream_run(request.query, request.session_id):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
