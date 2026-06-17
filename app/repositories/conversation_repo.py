from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.repositories.base import BaseRepository, PaginatedResponse


class ConversationRepo(BaseRepository[Conversation]):
    def __init__(self, session: AsyncSession):
        super().__init__(Conversation, session)

    async def list_by_user(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
    ) -> PaginatedResponse:
        stmt = select(Conversation).where(Conversation.user_id == user_id)
        count_stmt = select(func.count()).select_from(Conversation).where(Conversation.user_id == user_id)

        if search:
            stmt = stmt.where(Conversation.title.ilike(f"%{search}%"))
            count_stmt = count_stmt.where(Conversation.title.ilike(f"%{search}%"))

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(Conversation.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return PaginatedResponse(data=items, page=page, page_size=page_size, total=total)
