from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository, PaginatedResponse


class AuditRepo(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)

    async def record(
        self,
        operation: str,
        details: dict | None = None,
        ip_address: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        risk_level: str | None = None,
        status: str | None = None,
    ) -> AuditLog:
        if ip_address:
            parts = ip_address.rsplit(".", 1)
            if len(parts) == 2:
                ip_address = f"{parts[0]}.xxx"

        log = AuditLog(
            operation=operation,
            details=details,
            ip_address=ip_address,
            user_id=user_id,
            trace_id=trace_id,
            risk_level=risk_level,
            status=status,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def query_logs(
        self,
        page: int = 1,
        page_size: int = 20,
        operation: str | None = None,
        risk_level: str | None = None,
    ) -> PaginatedResponse:
        stmt = select(AuditLog)
        count_stmt = select(func.count()).select_from(AuditLog)

        if operation:
            stmt = stmt.where(AuditLog.operation == operation)
            count_stmt = count_stmt.where(AuditLog.operation == operation)
        if risk_level:
            stmt = stmt.where(AuditLog.risk_level == risk_level)
            count_stmt = count_stmt.where(AuditLog.risk_level == risk_level)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.order_by(AuditLog.created_at.desc())
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return PaginatedResponse(data=items, page=page, page_size=page_size, total=total)
