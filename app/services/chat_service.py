import asyncio
import json
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

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
            await self.msg_repo.create_message(
                conversation_id, role="user", content=message
            )
            logger.info(
                "chat_stream_start", conversation_id=conversation_id, user_id=user_id
            )

            graph = self.app.state.graph
            config = {
                "configurable": {"thread_id": conversation_id},
            }
            input_msg = {
                "messages": [{"role": "user", "content": message}],
                "conversation_id": conversation_id,
                "user_id": user_id,
                "skill_hint": skill_hint,
            }

            pending_ai_content: list[str] = []
            pending_tool_calls: list[dict] = []

            async for evt in stream_agent_response(graph, config, input_msg):
                yield evt.sse

                if evt.role == "assistant" and evt.content:
                    pending_ai_content.append(evt.content)

                if evt.role == "assistant" and evt.tool_calls:
                    pending_tool_calls = evt.tool_calls

                if evt.role == "tool":
                    if pending_ai_content or pending_tool_calls:
                        full_content = "".join(pending_ai_content)
                        await self.msg_repo.create_message(
                            conversation_id,
                            role="assistant",
                            content=full_content,
                            tool_calls=pending_tool_calls or None,
                        )
                        pending_ai_content = []
                        pending_tool_calls = []

                    await self.msg_repo.create_message(
                        conversation_id,
                        role="tool",
                        content=evt.content,
                        name=evt.name,
                        tool_call_id=evt.tool_call_id or None,
                    )

                if evt.is_end and (pending_ai_content or pending_tool_calls):
                    full_content = "".join(pending_ai_content)
                    await self.msg_repo.create_message(
                        conversation_id,
                        role="assistant",
                        content=full_content,
                        tool_calls=pending_tool_calls or None,
                    )

    async def confirm_hitl_stream(
        self,
        conversation_id: str,
        checkpoint_id: str,
        decision: str,
        context: dict | None,
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
                "context": context,
                "checkpoint_id": checkpoint_id,
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
        )

        if decision == "reject":
            await self.msg_repo.create_message(
                conversation_id,
                role="assistant",
                content="Operation rejected by user.",
            )
            reject_chunk = {
                "type": "hitl_rejected",
                "ns": ["main_agent"],
                "data": {
                    "conversation_id": conversation_id,
                    "decision": "reject",
                },
            }
            yield f"event: message\ndata: {json.dumps(reject_chunk, ensure_ascii=False)}\n\n"
            end_chunk = {
                "type": "end",
                "ns": [],
                "data": {"conversation_id": conversation_id, "reason": "user_rejected"},
            }
            yield f"event: end\ndata: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
            return

        graph = self.app.state.graph
        config = {
            "configurable": {"thread_id": conversation_id},
        }

        pending_ai_content: list[str] = []
        pending_tool_calls: list[dict] = []

        async for evt in stream_resume_response(graph, config, decision, context):
            yield evt.sse

            if evt.role == "assistant" and evt.content:
                pending_ai_content.append(evt.content)

            if evt.role == "assistant" and evt.tool_calls:
                pending_tool_calls = evt.tool_calls

            if evt.role == "tool":
                if pending_ai_content or pending_tool_calls:
                    full_content = "".join(pending_ai_content)
                    await self.msg_repo.create_message(
                        conversation_id,
                        role="assistant",
                        content=full_content,
                        tool_calls=pending_tool_calls or None,
                    )
                    pending_ai_content = []
                    pending_tool_calls = []

                await self.msg_repo.create_message(
                    conversation_id,
                    role="tool",
                    content=evt.content,
                    name=evt.name,
                    tool_call_id=evt.tool_call_id or None,
                )

            if evt.is_end and (pending_ai_content or pending_tool_calls):
                full_content = "".join(pending_ai_content)
                await self.msg_repo.create_message(
                    conversation_id,
                    role="assistant",
                    content=full_content,
                    tool_calls=pending_tool_calls or None,
                )
