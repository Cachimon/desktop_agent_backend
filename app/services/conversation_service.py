import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.schemas.conversation import (
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    PaginatedConversationResponse,
    PaginationMeta,
)
from app.utils.exceptions import ConversationNotFound, ConversationBusy


class ConversationService:
    def __init__(self, session: AsyncSession):
        self.conv_repo = ConversationRepo(session)
        self.msg_repo = MessageRepo(session)
        self.session = session

    async def create_conversation(self, user_id: str, title: str | None = None) -> ConversationResponse:
        conv = Conversation(id=str(uuid.uuid4()), user_id=user_id, title=title)
        conv = await self.conv_repo.create(conv)
        return ConversationResponse.model_validate(conv)

    async def list_conversations(
        self, user_id: str, page: int = 1, page_size: int = 20, search: str | None = None
    ) -> PaginatedConversationResponse:
        result = await self.conv_repo.list_by_user(user_id, page, page_size, search)
        return PaginatedConversationResponse(
            data=[ConversationResponse.model_validate(c) for c in result.data],
            pagination=PaginationMeta(**result.pagination),
        )

    async def get_conversation(self, conversation_id: str, user_id: str) -> ConversationDetailResponse:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")
        messages = await self.msg_repo.list_by_conversation(conversation_id)
        return ConversationDetailResponse(
            id=conv.id,
            user_id=conv.user_id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            messages=[MessageResponse.model_validate(m) for m in messages],
        )

    async def delete_conversation(self, conversation_id: str, user_id: str) -> None:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")
        await self.conv_repo.delete(conv)

    async def send_message(
        self, conversation_id: str, user_id: str, role: str, content: str, tool_calls: dict | None = None
    ) -> MessageResponse:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")
        msg = await self.msg_repo.create_message(conversation_id, role, content, tool_calls)
        return MessageResponse.model_validate(msg)
