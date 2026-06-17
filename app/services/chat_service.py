import asyncio
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_graph
from app.agents.streaming import stream_agent_response
from app.repositories.conversation_repo import ConversationRepo
from app.repositories.message_repo import MessageRepo
from app.security.audit_logger import record_audit
from app.utils.exceptions import ConversationNotFound, ConversationBusy, CheckpointNotFound
from app.utils.logging import get_logger

logger = get_logger(__name__)

_active_streams: dict[str, asyncio.Lock] = {}


class ChatService:
    def __init__(self, session: AsyncSession):
        self.session = session
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
            await self.msg_repo.create_message(conversation_id, "user", message)
            logger.info("chat_stream_start", conversation_id=conversation_id, user_id=user_id)

            graph = build_graph()
            config = {
                "configurable": {"thread_id": conversation_id},
            }
            input_msg = {
                "messages": [{"role": "user", "content": message}],
                "conversation_id": conversation_id,
                "user_id": user_id,
                "skill_hint": skill_hint,
            }

            async for chunk in stream_agent_response(graph, config, input_msg):
                yield chunk

    async def confirm_hitl(
        self,
        conversation_id: str,
        checkpoint_id: str,
        decision: str,
        context: dict | None,
        user_id: str,
    ) -> dict:
        conv = await self.conv_repo.get_by_id(conversation_id)
        if not conv or conv.user_id != user_id:
            raise ConversationNotFound(message="Conversation not found")

        operation = "hitl_confirm" if decision == "approve" else "hitl_reject"
        await record_audit(
            self.session,
            operation=operation,
            details={"decision": decision, "context": context, "checkpoint_id": checkpoint_id},
            user_id=user_id,
            risk_level="medium" if decision == "approve" else "low",
            status="completed",
        )

        return {
            "status": "confirmed" if decision == "approve" else "rejected",
            "conversation_id": conversation_id,
            "checkpoint_id": checkpoint_id,
            "decision": decision,
        }
