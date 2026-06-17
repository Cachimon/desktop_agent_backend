from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.repositories.audit_repo import AuditRepo
from app.schemas.conversation import PaginationMeta
from app.utils.exceptions import NotImplementError

router = APIRouter(tags=["Reserved"])


@router.get("/mcp/servers")
@router.post("/mcp/servers")
async def mcp_servers():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 2+"},
    )


@router.get("/mcp/tools")
@router.post("/mcp/tools")
async def mcp_tools():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 2+"},
    )


@router.get("/agents/sub")
@router.post("/agents/sub")
async def agents_sub():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 3+"},
    )


@router.get("/search/semantic")
async def search_semantic():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 2+"},
    )


@router.post("/files/organize")
async def files_organize():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 2+"},
    )


@router.get("/tasks")
async def tasks():
    raise NotImplementError(
        message="This endpoint is reserved for a future phase",
        detail={"phase": "Phase 2+"},
    )
