import json
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator

from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.graph import StateGraph
from langgraph.types import Command

from app.agents.state import AgentState

from langgraph.stream.run_stream import AsyncGraphRunStream


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
    graph: StateGraph, config: dict, input_message: AgentState, conversation_id: str, interrupt_id: str = ''
):

    # 用于累积完整回答（如果需要）
    full_response = ""
    # 用于存储本次会话的完整消息列表（最终持久化）
    collected_messages = []

    try:
        # 5. 调用 astream_events v3
        if interrupt_id:
            stream: AsyncGraphRunStream = await graph.astream_events(
                Command(resume=input_message), config=config, version="v3"
            )
        else:
            stream: AsyncGraphRunStream = await graph.astream_events(
                input_message,
                config=config,
                version="v3",  # 必须指定
            )

        # 6. 消费 messages 投影（获取 LLM 输出）
        #    stream.messages 是异步迭代器，每个元素是一个 ChatModelStream 对象
        async for message_stream in stream.messages:
            # 6a. 逐字输出文本块（打字机效果）
            async for token in message_stream.text:
                if token:
                    full_response += token
                    yield StreamEvent(
                        sse=f"data: {json.dumps({'type': 'ai', 'data': {'content': token}}, ensure_ascii=False)}\n\n",
                        role="assistant",
                        content=token,
                    )

            # 6b. 如果有工具调用，这里可以处理
            # 工具调用参数也是流式的，但为了简化，我们可以等到最终消息
            # 或者使用 message_stream.tool_calls 迭代
            # 例如，在工具调用完成时获取完整工具调用
            # 但通常我们更关心最终的工具调用列表，可以在 message_stream.output 中获取
            async for tool_call in message_stream.tool_calls:
                # 如果只想在工具调用完成时获取完整信息，可以用 await message.output
                # 然后从 output 中提取 tool_calls
                pass

            # 6c. 获取本次 LLM 调用的完整输出（AIMessage）
            final_ai_message = await message_stream.output
            if final_ai_message:
                # 存储完整的 AI 消息（包含 tool_calls）
                # 注意：可能会多次输出（如果有多次 LLM 调用），我们只存最终的
                # 这里可以根据需要存储，但为了简化，我们在流结束后统一存储
                # 或者我们可以先收集到列表
                pass
        print("流结束了============", stream, await stream.interrupted(), await stream.interrupts())
        # 7. 流结束后，检查是否有中断
        if await stream.interrupted():
            for interrupt_data in await stream.interrupts():
                # 必须包括interrupt_id、message、action、type（目前暂定confirm一种）
                interrupt_data = interrupt_data.value
                interrupt_data["conversation_id"] = conversation_id
                yield StreamEvent(
                    sse=f"data: {json.dumps({'type': 'human', 'data': interrupt_data}, ensure_ascii=False)}\n\n",
                    role="assistant",
                    content=interrupt_data.get("message", ""),
                    is_end=True,
                )
            return  # 再次中断，等待下一次恢复
            # 停止流，等待前端调用 /resume 恢复
            # 注意：这里不存储消息（因为会话未完成），但可以先保存已生成的片段？
            # 通常中断后，之前生成的 token 已经通过 SSE 发送了，但未完整存储，可以暂存到内存，恢复后继续。
            # 这里简化处理，不存储部分消息，等最终完成再存。

        # 发送完成事件
        yield StreamEvent(
            sse=f"data: {json.dumps({'type': 'end', 'data': {'content': full_response}}, ensure_ascii=False)}\n\n",
            role="assistant",
            content=full_response,
            is_end=True,
        )

    except Exception as e:
        # 异常处理
        import traceback

        traceback.print_exc()
        yield StreamEvent(
            sse=f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n",
            role="assistant",
            content=str(e),
            is_end=True,
        )


# ---------- 恢复中断的生成器 ----------
async def stream_resume_response(
    graph: StateGraph,
    config: dict,
    decision: str,
    interrupt_id: str,
    conversation_id: str,
):
    # 构造恢复命令
    resume_value = {
        interrupt_id: {
            "decision": decision,
        },
    }

    try:
        # 重新调用 astream_events，传入 Command
        stream: AsyncGraphRunStream = await graph.astream_events(
            Command(resume=resume_value), config=config, version="v3"
        )

        # 与正常流类似，处理输出
        full_response = ""
        async for message_stream in stream.messages:
            async for token in message_stream.text:
                if token:
                    full_response += token
                    yield StreamEvent(
                        sse=f"data: {json.dumps({'type': 'ai', 'data': {'content': token}}, ensure_ascii=False)}\n\n",
                        role="assistant",
                        content=token,
                    )
            async for tool_call in message_stream.tool_calls:
                # 如果只想在工具调用完成时获取完整信息，可以用 await message.output
                # 然后从 output 中提取 tool_calls
                pass

            # 6c. 获取本次 LLM 调用的完整输出（AIMessage）
            final_ai_message = await message_stream.output
            if final_ai_message:
                # 存储完整的 AI 消息（包含 tool_calls）
                # 注意：可能会多次输出（如果有多次 LLM 调用），我们只存最终的
                # 这里可以根据需要存储，但为了简化，我们在流结束后统一存储
                # 或者我们可以先收集到列表
                print("final_ai_message===============", final_ai_message)
        print("流结束了============", stream, await stream.interrupted(), await stream.interrupts())
        # 7. 流结束后，检查是否有中断
        if await stream.interrupted():
            for interrupt_data in await stream.interrupts():
                # 必须包括interrupt_id、message、action、type（目前暂定confirm一种）
                interrupt_data = interrupt_data.value
                interrupt_data["conversation_id"] = conversation_id
                yield StreamEvent(
                    sse=f"data: {json.dumps({'type': 'human', 'data': interrupt_data}, ensure_ascii=False)}\n\n",
                    role="assistant",
                    content=interrupt_data.get("message", ""),
                    is_end=True,
                )
            return  # 再次中断，等待下一次恢复

        yield StreamEvent(
            sse=f"data: {json.dumps({'type': 'end', 'data': {'content': full_response}}, ensure_ascii=False)}\n\n",
            role="assistant",
            content=full_response,
            is_end=True,
        )

    except Exception as e:
        import traceback

        traceback.print_exc()
        yield StreamEvent(
            sse=f"data: {json.dumps({'type': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n",
            role="assistant",
            content=str(e),
            is_end=True,
        )


async def stream_agent_response1(
    graph: StateGraph,
    config: dict,
    input_message: AgentState,
) -> AsyncGenerator[StreamEvent, None]:
    conversation_id = config.get("configurable", {}).get("thread_id", "")

    try:
        # 1. 调用 v3 API，返回 Run 流对象
        stream = await graph.astream_events(
            input_message,
            config=config,
            version="v3",  # 关键：必须指定 v3
        )

        # 2. 直接消费 messages 投影
        async for message in stream.messages:
            # 每个 message 是一个 ChatModelStream 对象，包含多个投影

            # 2a. 获取文本块（实现打字机效果）
            async for token in message.text:
                # 这里 token 就是 LLM 输出的单个文本块
                msg_data = {
                    "type": "ai",
                    "ns": ["main_agent"],
                    "data": {"content": token, "tool_calls": []},
                    "message_id": str(id(token)),
                }
                # 构建 SSE 事件并推送
                yield StreamEvent(
                    sse=build_sse(event="message", data=msg_data),
                    role="assistant",
                    content=token,
                )

            # 2b. 获取工具调用（如果有）
            # 注意：tool_calls 也是流式的，可以逐块获取
            async for tool_call in message.tool_calls:
                # 如果只想在工具调用完成时获取完整信息，可以用 await message.output
                # 然后从 output 中提取 tool_calls
                pass

            # 2c. 获取最终完整的消息对象（包含所有 tool_calls）
            final_message = await message.output
            if final_message.tool_calls:
                # 这里处理完整的工具调用列表
                tool_calls = [
                    {
                        "name": tc.get("name"),
                        "args": tc.get("args", {}),
                        "id": tc.get("id"),
                    }
                    for tc in final_message.tool_calls
                ]
                # 然后构建相应的 SSE 事件
                # ...

        async for event in graph.astream_events(
            input_message,
            config=config,
            version="v3",
        ):
            parsed = _parse_event(event, conversation_id)
            if parsed:
                yield parsed

            if event.get("event") == "on_interrupt":
                state = await graph.aget_state(config)
                print("用户中断啦，state.next", state.next)
                hitl_data = {
                    "type": "human",
                    "ns": ["main_agent", "__interrupt__"],
                    "data": {
                        "action": "confirm",
                        "message": _extract_interrupt_message(state),
                        "conversation_id": conversation_id,
                        "checkpoint_id": state.config.get("configurable", {}).get(
                            "checkpoint_id", ""
                        ),
                        "next_nodes": list(state.next),
                        "context": _extract_interrupt_context(state),
                    },
                    "message_id": "",
                }
                yield StreamEvent(
                    sse=_build_sse("message", hitl_data),
                    is_hitl=True,
                )
                return

        # state = await graph.aget_state(config)
        # if state.next:
        #     hitl_data = {
        #         "type": "human",
        #         "ns": ["main_agent", "__interrupt__"],
        #         "data": {
        #             "action": "confirm",
        #             "message": _extract_interrupt_message(state),
        #             "conversation_id": conversation_id,
        #             "checkpoint_id": state.config.get("configurable", {}).get(
        #                 "checkpoint_id", ""
        #             ),
        #             "next_nodes": list(state.next),
        #             "context": _extract_interrupt_context(state),
        #         },
        #         "message_id": "",
        #     }
        #     yield StreamEvent(
        #         sse=_build_sse("message", hitl_data),
        #         is_hitl=True,
        #     )
        #     return

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
            "message_id": "",
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


async def stream_resume_response1(
    graph: StateGraph,
    config: dict,
    decision: str,
) -> AsyncGenerator[StreamEvent, None]:
    conversation_id = config.get("configurable", {}).get("thread_id", "")

    try:
        resume_value = {
            "decision": decision,
        }

        async for event in graph.astream_events(
            Command(resume=resume_value),
            config=config,
            version="v3",
        ):
            parsed = _parse_event(event, conversation_id)
            if parsed:
                yield parsed
            if event.get("event") == "on_interrupt":
                state = await graph.aget_state(config)
                hitl_data = {
                    "type": "human",
                    "ns": ["main_agent", "__interrupt__"],
                    "data": {
                        "action": "confirm",
                        "message": _extract_interrupt_message(state),
                        "conversation_id": conversation_id,
                        "checkpoint_id": state.config.get("configurable", {}).get(
                            "checkpoint_id", ""
                        ),
                        "next_nodes": list(state.next),
                        "context": _extract_interrupt_context(state),
                    },
                    "message_id": "",
                }
                yield StreamEvent(
                    sse=_build_sse("message", hitl_data),
                    is_hitl=True,
                )
                return

        # state = await graph.aget_state(config)
        # if state.next:
        #     hitl_data = {
        #         "type": "human",
        #         "ns": ["main_agent", "__interrupt__"],
        #         "data": {
        #             "action": "confirm",
        #             "message": _extract_interrupt_message(state),
        #             "conversation_id": conversation_id,
        #             "checkpoint_id": state.config.get("configurable", {}).get(
        #                 "checkpoint_id", ""
        #             ),
        #             "next_nodes": list(state.next),
        #             "context": _extract_interrupt_context(state),
        #         },
        #         "message_id": "",
        #     }
        #     yield StreamEvent(
        #         sse=_build_sse("message", hitl_data),
        #         is_hitl=True,
        #     )
        #     return

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
            "message_id": "",
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


def _extract_interrupt_message(state) -> str:
    tasks = state.tasks
    print("================task", tasks)
    for task in tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            for intr in task.interrupts:
                if isinstance(intr.value, dict):
                    return intr.value.get("message", "Confirmation required")
                return str(intr.value)
    values = state.values if hasattr(state, "values") else {}
    if "__interrupt__" in values:
        interrupts = values["__interrupt__"]
        if interrupts and hasattr(interrupts[0], "value"):
            val = interrupts[0].value
            if isinstance(val, dict):
                return val.get("message", "Confirmation required")
            return str(val)
    return "Confirmation required"


def _extract_interrupt_context(state) -> dict | None:
    tasks = state.tasks
    for task in tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            for intr in task.interrupts:
                if isinstance(intr.value, dict):
                    return intr.value.get("context", intr.value)
                return {"value": intr.value}
    values = state.values if hasattr(state, "values") else {}
    if "__interrupt__" in values:
        interrupts = values["__interrupt__"]
        if interrupts and hasattr(interrupts[0], "value"):
            val = interrupts[0].value
            if isinstance(val, dict):
                return val.get("context", val)
            return {"value": val}
    return None


def _parse_event(event: dict, conversation_id: str) -> StreamEvent | None:
    kind = event.get("event", "")
    data = event.get("data", {})
    name = event.get("name", "")

    if kind == "on_chat_model_stream":
        print("智能体输出的东西=================", event)
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
        print("智能体输出的东西=================", event)
        output = data.get("output")
        if output:
            tool_calls_raw = getattr(output, "tool_calls", None) or []
            if tool_calls_raw:
                tool_calls = [
                    {
                        "name": tc.get("name"),
                        "args": tc.get("args", {}),
                        "id": tc.get("id"),
                    }
                    for tc in tool_calls_raw
                ]
                # TODO: tool_calling干嘛的啊，好烦啊怎么这么多状态
                msg_data = {
                    "type": "tool_calling",
                    "ns": ["main_agent"],
                    "data": {"content": "", "tool_calls": tool_calls},
                    "message_id": str(id(output)),
                }
                return StreamEvent(
                    sse=_build_sse("message", msg_data),
                    role="assistant",
                    content="",
                    tool_calls=tool_calls,
                )

    elif kind == "on_tool_start":
        print("智能体输出的东西=================", event)
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
        print("智能体输出的东西=================", event)
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
