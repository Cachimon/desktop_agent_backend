from typing import Literal

from pydantic import BaseModel


class ComponentStatus(BaseModel):
    status: str
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    components: dict[str, ComponentStatus]
