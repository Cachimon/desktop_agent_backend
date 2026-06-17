from math import ceil
from typing import Any, Generic, TypeVar, Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class PaginatedResponse:
    def __init__(self, data: list, page: int, page_size: int, total: int):
        self.data = data
        self.pagination = {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": ceil(total / page_size) if page_size > 0 else 0,
            "has_next": page * page_size < total,
            "has_prev": page > 1,
        }


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: Any) -> ModelType | None:
        return await self.session.get(self.model, id)

    async def get_all(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict | None = None,
        order_by: Any = None,
    ) -> PaginatedResponse:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)

        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key) and value is not None:
                    col = getattr(self.model, key)
                    stmt = stmt.where(col == value)
                    count_stmt = count_stmt.where(col == value)

        if order_by is not None:
            stmt = stmt.order_by(order_by)
        else:
            if hasattr(self.model, "created_at"):
                stmt = stmt.order_by(self.model.created_at.desc())

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return PaginatedResponse(data=items, page=page, page_size=page_size, total=total)

    async def create(self, obj: ModelType) -> ModelType:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: ModelType, data: dict) -> ModelType:
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelType) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def get_one(self, stmt: Select) -> ModelType | None:
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_many(self, stmt: Select) -> Sequence[ModelType]:
        result = await self.session.execute(stmt)
        return result.scalars().all()
