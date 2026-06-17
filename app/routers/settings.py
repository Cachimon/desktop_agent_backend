from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.schemas.settings import WorkspaceAddRequest, WorkspaceAddResponse, WorkspaceListResponse
from app.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/workspace", response_model=WorkspaceListResponse)
async def get_workspaces(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = WorkspaceService(session)
    return await svc.get_workspaces(user["sub"])


@router.post("/workspace", response_model=WorkspaceAddResponse)
async def manage_workspace(
    body: WorkspaceAddRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    svc = WorkspaceService(session)
    if body.action == "add":
        return await svc.add_workspace(user["sub"], body.path, body.alias, body.confirm_level)
    else:
        result = await svc.remove_workspace(user["sub"], body.path)
        return result
