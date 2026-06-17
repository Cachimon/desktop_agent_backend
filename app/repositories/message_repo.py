from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.repositories.base import BaseRepository


class MessageRepo(BaseRepository[Message]):
    def __init__(self, session: AsyncSession):
        super().__init__(Message, session)

    async def list_by_conversation(self, conversation_id: str) -> list[Message]:
        stmt = select(Message).where(Message.conversation_id == conversation_id).order_by(Message.created_at.asc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_message(
        self, conversation_id: str, role: str, content: str, tool_calls: dict | None = None
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
        )
        return await self.create(msg)
