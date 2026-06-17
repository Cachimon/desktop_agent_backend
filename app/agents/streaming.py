import json
import asyncio
from typing import AsyncGenerator

from langgraph.graph import StateGraph

from app.agents.state import AgentState


async def stream_agent_response(
    graph: StateGraph,
    config: dict,
    input_message: dict,
) -> AsyncGenerator[str, None]:
    conversation_id = config.get("configurable", {}).get("thread_id", "")

    try:
        async for event in graph.astream_events(
            input_message,
            config=config,
            version="v2",
        ):
            chunk = _transform_event(event, conversation_id)
            if chunk:
                yield f"event: message\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        end_chunk = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield f"event: end\ndata: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"

    except asyncio.CancelledError:
        end_chunk = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id, "reason": "cancelled"},
        }
        yield f"event: end\ndata: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
    except Exception as e:
        error_chunk = {
            "type": "error",
            "ns": ["main_agent"],
            "data": {"content": str(e)},
        }
        yield f"event: message\ndata: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
        end_chunk = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield f"event: end\ndata: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"


def _transform_event(event: dict, conversation_id: str) -> dict | None:
    kind = event.get("event", "")
    data = event.get("data", {})
    name = event.get("name", "")
    tags = event.get("tags", [])

    if kind == "on_chat_model_stream":
        chunk_data = data.get("chunk")
        if chunk_data:
            content = getattr(chunk_data, "content", "")
            if content:
                return {
                    "type": "ai",
                    "ns": ["main_agent"],
                    "data": {"content": content, "tool_calls": []},
                    "message_id": str(id(chunk_data)),
                }

    elif kind == "on_tool_start":
        return {
            "type": "tool",
            "ns": ["main_agent", "tools"],
            "data": {"name": name, "input": data.get("input", {})},
            "message_id": "",
        }

    elif kind == "on_tool_end":
        return {
            "type": "tool",
            "ns": ["main_agent", "tools"],
            "data": {"name": name, "output": str(data.get("output", ""))},
            "message_id": "",
        }

    return None
