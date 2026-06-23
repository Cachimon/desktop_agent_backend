import json
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator

from langgraph.graph import StateGraph
from langgraph.types import Command

from app.agents.state import AgentState


@dataclass
class StreamEvent:
    sse: str
    role: str = ""
    content: str = ""
    name: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    tool_call_id: str = ""
    is_end: bool = False
    is_hitl: bool = False
    is_error: bool = False


def _build_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_agent_response(
    graph: StateGraph,
    config: dict,
    input_message: dict,
) -> AsyncGenerator[StreamEvent, None]:
    conversation_id = config.get("configurable", {}).get("thread_id", "")

    try:
        async for event in graph.astream_events(
            input_message,
            config=config,
            version="v2",
        ):
            parsed = _parse_event(event, conversation_id)
            if parsed:
                yield parsed

        state = await graph.aget_state(config)
        if state.next:
            hitl_data = {
                "type": "hitl_required",
                "ns": ["main_agent"],
                "data": {
                    "conversation_id": conversation_id,
                    "checkpoint_id": state.config.get("configurable", {}).get(
                        "checkpoint_id", ""
                    ),
                    "next_nodes": list(state.next),
                    "context": state.values.get("hitl_context"),
                },
            }
            yield StreamEvent(
                sse=_build_sse("hitl", hitl_data),
                is_hitl=True,
            )
            return

        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )

    except asyncio.CancelledError:
        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id, "reason": "cancelled"},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )
    except Exception as e:
        error_data = {
            "type": "error",
            "ns": ["main_agent"],
            "data": {"content": str(e)},
        }
        yield StreamEvent(
            sse=_build_sse("message", error_data),
            is_error=True,
            role="assistant",
            content=str(e),
        )
        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )


async def stream_resume_response(
    graph: StateGraph,
    config: dict,
    decision: str,
    context: dict | None = None,
) -> AsyncGenerator[StreamEvent, None]:
    conversation_id = config.get("configurable", {}).get("thread_id", "")

    try:
        resume_value = {
            "decision": decision,
            "context": context,
        }

        async for event in graph.astream_events(
            Command(resume=resume_value),
            config=config,
            version="v2",
        ):
            parsed = _parse_event(event, conversation_id)
            if parsed:
                yield parsed

        state = await graph.aget_state(config)
        if state.next:
            hitl_data = {
                "type": "hitl_required",
                "ns": ["main_agent"],
                "data": {
                    "conversation_id": conversation_id,
                    "checkpoint_id": state.config.get("configurable", {}).get(
                        "checkpoint_id", ""
                    ),
                    "next_nodes": list(state.next),
                    "context": state.values.get("hitl_context"),
                },
            }
            yield StreamEvent(
                sse=_build_sse("hitl", hitl_data),
                is_hitl=True,
            )
            return

        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )

    except asyncio.CancelledError:
        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id, "reason": "cancelled"},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )
    except Exception as e:
        error_data = {
            "type": "error",
            "ns": ["main_agent"],
            "data": {"content": str(e)},
        }
        yield StreamEvent(
            sse=_build_sse("message", error_data),
            is_error=True,
            role="assistant",
            content=str(e),
        )
        end_data = {
            "type": "end",
            "ns": [],
            "data": {"conversation_id": conversation_id},
        }
        yield StreamEvent(
            sse=_build_sse("end", end_data),
            is_end=True,
        )


def _parse_event(event: dict, conversation_id: str) -> StreamEvent | None:
    kind = event.get("event", "")
    data = event.get("data", {})
    name = event.get("name", "")

    if kind == "on_chat_model_stream":
        chunk_data = data.get("chunk")
        if chunk_data:
            content = getattr(chunk_data, "content", "")
            if content:
                msg_data = {
                    "type": "ai",
                    "ns": ["main_agent"],
                    "data": {"content": content, "tool_calls": []},
                    "message_id": str(id(chunk_data)),
                }
                return StreamEvent(
                    sse=_build_sse("message", msg_data),
                    role="assistant",
                    content=content,
                )

    elif kind == "on_chat_model_end":
        output = data.get("output")
        if output:
            content = getattr(output, "content", "") or ""
            tool_calls_raw = getattr(output, "tool_calls", None) or []
            tool_calls = [
                {"name": tc.get("name"), "args": tc.get("args", {}), "id": tc.get("id")}
                for tc in tool_calls_raw
            ]
            if content or tool_calls:
                msg_data = {
                    "type": "ai",
                    "ns": ["main_agent"],
                    "data": {"content": content, "tool_calls": tool_calls},
                    "message_id": str(id(output)),
                }
                return StreamEvent(
                    sse=_build_sse("message", msg_data),
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                )

    elif kind == "on_tool_start":
        tool_input = data.get("input", {})
        tc_id = (
            tool_input.get("tool_call_id", "") if isinstance(tool_input, dict) else ""
        )
        tool_data = {
            "type": "tool",
            "ns": ["main_agent", "tools"],
            "data": {"name": name, "input": tool_input},
            "message_id": "",
        }
        return StreamEvent(
            sse=_build_sse("message", tool_data),
            role="tool",
            name=name,
            tool_call_id=tc_id,
        )

    elif kind == "on_tool_end":
        output_str = str(data.get("output", ""))
        tc_id = ""
        output_data = data.get("output")
        if hasattr(output_data, "tool_call_id"):
            tc_id = output_data.tool_call_id
        tool_data = {
            "type": "tool",
            "ns": ["main_agent", "tools"],
            "data": {"name": name, "output": output_str},
            "message_id": "",
        }
        return StreamEvent(
            sse=_build_sse("message", tool_data),
            role="tool",
            name=name,
            content=output_str,
            tool_call_id=tc_id,
        )

    return None
