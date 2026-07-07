import operator
from typing import TypedDict, Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    conversation_id: str
    user_id: str
    skill_hint: str | None
    error: str | None
    pending_confirm: dict | None
    check_skill_hint: bool = False
    loaded_skill: bool = False
    guide: str | None
    activated_skills: list[str]
    subagent_task: dict | None



class SkillAgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    activated_skills: list[str]
    subagent_task: dict | None