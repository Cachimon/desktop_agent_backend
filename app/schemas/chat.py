from typing import Literal

from pydantic import BaseModel


class ChatStreamRequest(BaseModel):
    conversation_id: str
    message: str
    skill_hint: str | None = None
    stream_mode: str = "messages"


class HITLConfirmRequest(BaseModel):
    conversation_id: str
    checkpoint_id: str
    decision: Literal["approve", "reject"]
    context: dict | None = None


class HITLConfirmResponse(BaseModel):
    status: str
    conversation_id: str
    checkpoint_id: str
    decision: str
