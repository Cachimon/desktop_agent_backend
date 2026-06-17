from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: str | None = None


class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    tool_calls: list | None = None


class MessageResponse(BaseModel):
    id: int
    conversation_id: str
    role: str
    content: str
    tool_calls: list | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationDetailResponse(BaseModel):
    id: str
    user_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PaginatedConversationResponse(BaseModel):
    data: list[ConversationResponse]
    pagination: PaginationMeta
