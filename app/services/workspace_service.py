from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.settings_repo import SettingsRepo
from app.schemas.settings import (
    WorkspaceAddResponse,
    WorkspaceConfig,
    WorkspaceListResponse,
)
from app.security.path_validator import check_path_security, PathSecurityLevel
from app.utils.exceptions import PathForbiddenError, WorkspaceAlreadyExists


class WorkspaceService:
    def __init__(self, session: AsyncSession):
        self.repo = SettingsRepo(session)

    async def get_workspaces(self, user_id: str) -> WorkspaceListResponse:
        setting = await self.repo.get_user_setting(user_id, "workspace")
        if not setting or not setting.setting_value:
            return WorkspaceListResponse(workspaces=[])
        workspaces = [
            WorkspaceConfig(**ws) for ws in setting.setting_value.get("items", [])
        ]
        return WorkspaceListResponse(workspaces=workspaces)

    async def add_workspace(
        self, user_id: str, path: str, alias: str | None, confirm_level: str
    ) -> WorkspaceAddResponse:
        level, reason = await check_path_security(path)
        if level == PathSecurityLevel.FORBIDDEN:
            raise PathForbiddenError(message=reason)

        setting = await self.repo.get_user_setting(user_id, "workspace")
        items = setting.setting_value.get("items", []) if setting and setting.setting_value else []

        for ws in items:
            if ws["path"] == path:
                raise WorkspaceAlreadyExists(message="Workspace already exists")

        new_ws = {
            "path": path,
            "alias": alias,
            "added_at": datetime.utcnow().isoformat(),
            "confirm_level": confirm_level,
        }
        items.append(new_ws)
        await self.repo.set_user_setting(user_id, "workspace", {"items": items})

        return WorkspaceAddResponse(
            path=path, alias=alias, confirm_level=confirm_level, added_at=datetime.utcnow()
        )

    async def remove_workspace(self, user_id: str, path: str) -> dict:
        setting = await self.repo.get_user_setting(user_id, "workspace")
        if not setting or not setting.setting_value:
            return {"message": "Workspace not found"}

        items = setting.setting_value.get("items", [])
        items = [ws for ws in items if ws["path"] != path]
        await self.repo.set_user_setting(user_id, "workspace", {"items": items})
        return {"message": "Workspace removed"}
