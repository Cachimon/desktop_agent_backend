from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WorkspaceConfig(BaseModel):
    path: str
    alias: str | None
    added_at: datetime
    confirm_level: Literal["low", "high"]


class WorkspaceAddRequest(BaseModel):
    action: Literal["add", "remove"]
    path: str
    alias: str | None = None
    confirm_level: Literal["low", "high"] = "low"


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceConfig]


class WorkspaceAddResponse(BaseModel):
    path: str
    alias: str | None
    confirm_level: str
    added_at: datetime
