from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailResponse,
    ConversationResponse,
    MessageCreate,
    MessageResponse,
    PaginatedConversationResponse,
)
from app.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ConversationService(session)
    return await svc.create_conversation(user["sub"], body.title)


@router.get("", response_model=PaginatedConversationResponse)
async def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ConversationService(session)
    return await svc.list_conversations(user["sub"], page, page_size, search)


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ConversationService(session)
    return await svc.get_conversation(conversation_id, user["sub"])


@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ConversationService(session)
    await svc.delete_conversation(conversation_id, user["sub"])
    return {"message": "Conversation deleted"}


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=201)
async def send_message(
    conversation_id: str,
    body: MessageCreate,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = ConversationService(session)
    return await svc.send_message(
        conversation_id, user["sub"], body.role, body.content, body.tool_calls
    )
