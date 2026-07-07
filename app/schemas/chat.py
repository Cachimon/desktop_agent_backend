from typing import Literal

from pydantic import BaseModel


class ChatStreamRequest(BaseModel):
    conversation_id: str
    message: str
    skill_hint: str | None = None
    stream_mode: str = "messages"
    interrupt_id: str | None = None


class HITLConfirmRequest(BaseModel):
    conversation_id: str
    interrupt_id: str
    decision: Literal["approve", "reject"]
