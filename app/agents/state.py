from typing import TypedDict


class AgentState(TypedDict, total=False):
    messages: list[dict]
    conversation_id: str
    user_id: str
    skill_hint: str | None
    current_plan: str | None
    tool_results: list[dict] | None
    hitl_required: bool
    hitl_context: dict | None
    error: str | None
