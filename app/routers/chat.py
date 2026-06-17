from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.schemas.chat import ChatStreamRequest, HITLConfirmRequest, HITLConfirmResponse
from app.services.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChatService(session)
    generator = svc.stream_chat(
        conversation_id=body.conversation_id,
        message=body.message,
        user_id=user["sub"],
        skill_hint=body.skill_hint,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/hitl/confirm", response_model=HITLConfirmResponse)
async def hitl_confirm(
    body: HITLConfirmRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ChatService(session)
    result = await svc.confirm_hitl(
        conversation_id=body.conversation_id,
        checkpoint_id=body.checkpoint_id,
        decision=body.decision,
        context=body.context,
        user_id=user["sub"],
    )
    return HITLConfirmResponse(**result)
