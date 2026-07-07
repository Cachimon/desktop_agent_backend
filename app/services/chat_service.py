import asyncio
import json
from typing import AsyncGenerator, Any

from fastapi import FastAPI
from langchain_core.messages import HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.agents.streaming import (
    StreamEvent,
    stream_agent_response,
    stream_resume_response,
)
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.security.audit_logger import record_audit
from app.utils.exceptions import (
    ConversationNotFound,
    ConversationBusy,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

_active_streams: dict[str, asyncio.Lock] = {}


class ChatService:
    def __init__(self, session: AsyncSession, app: FastAPI):
        self.session = session
        self.app = app
        self.conv_repo = ConversationRepo(session)
        self.msg_repo = MessageRepo(session)

    async def stream_chat(
        self,
        conversation_id: str,
        message: str,
        user_id: str,
        skill_hint: str | None = None,
        interrupt_id: str | None = None,
    ) -> AsyncGenerator[str, None]:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")
        if conversation_id not in _active_streams:
            _active_streams[conversation_id] = asyncio.Lock()

        lock = _active_streams[conversation_id]
        if lock.locked():
            raise ConversationBusy(message="Conversation is already being processed")

        async with lock:
            print("用户指令", message)
            logger.info(
                "chat_stream_start", conversation_id=conversation_id, user_id=user_id
            )

            graph = self.app.state.graph
            config = {
                "configurable": {"thread_id": conversation_id},
            }
            input_msg: AgentState | dict[str, Any]
            if interrupt_id:
                input_msg = {
                    interrupt_id: {
                        "decision": message,
                    },
                }
            else:

                input_msg = AgentState(
                    messages=[HumanMessage(content=message)],
                    conversation_id=conversation_id,
                    user_id=user_id,
                    skill_hint=skill_hint,
                    check_skill_hint=False,
                    loaded_skill=False,
                    pending_confirm=None,
                    error=None,
                    guide=None,
                )

            async for evt in stream_agent_response(graph, config, input_msg, conversation_id, interrupt_id):
                yield evt.sse

                if evt.is_end:
                    return


    async def confirm_hitl_stream(
            self,
            conversation_id: str,
            interrupt_id: str,
            decision: str,
            user_id: str,
    ) -> AsyncGenerator[str, None]:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")

        operation = "hitl_confirm" if decision == "approve" else "hitl_reject"
        await record_audit(
            self.session,
            operation=operation,
            details={
                "decision": decision,
                "interrupt_id": interrupt_id,
            },
            user_id=user_id,
            risk_level="medium" if decision == "approve" else "low",
            status="completed",
        )

        logger.info(
            "hitl_confirm",
            conversation_id=conversation_id,
            decision=decision,
            user_id=user_id,
            interrupt_id=interrupt_id,
        )

        graph = self.app.state.graph
        config = {
            "configurable": {"thread_id": conversation_id},
        }

        async for evt in stream_resume_response(graph, config, decision, interrupt_id, conversation_id):
            yield evt.sse

            if evt.is_end:
                return

