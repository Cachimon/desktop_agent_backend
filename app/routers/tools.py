from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.repositories.audit_repo import AuditRepo
from app.schemas.conversation import PaginationMeta

router = APIRouter(prefix="/tools", tags=["Tools"])


@router.get("/calls")
async def tool_calls_audit(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    operation: str | None = Query(None),
    risk_level: str | None = Query(None),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    repo = AuditRepo(session)
    result = await repo.query_logs(page, page_size, operation, risk_level)
    return {
        "data": [
            {
                "id": log.id,
                "operation": log.operation,
                "details": log.details,
                "risk_level": log.risk_level,
                "status": log.status,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in result.data
        ],
        "pagination": PaginationMeta(**result.pagination),
    }
