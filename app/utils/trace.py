import uuid
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def get_trace_id() -> str:
    tid = _trace_id.get()
    if not tid:
        tid = generate_trace_id()
        _trace_id.set(tid)
    return tid


def set_trace_id(trace_id: str) -> None:
    _trace_id.set(trace_id)
