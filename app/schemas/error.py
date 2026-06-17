from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    detail: dict | None = None
    trace_id: str
