import asyncio
import json
import uuid
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

from app.agents.llm import get_llm
from app.agents.state import AgentState
from app.agents.tools.agent_tools import get_agent_tool
from app.agents.tools.skill_tools import get_skill_tools
from app.agents.utils.prompt_utils import (
    get_sys_prompt,
    build_layer1_prompt,
    build_layer2_prompt,
)
from app.agents.utils.agent_utils import load_bundled_resource, execute_tool_call
from app.security.path_validator import HITLRequiredError, SecurityError
from app.utils.logging import get_logger
from app.services.skill_service import get_skill_registry

logger = get_logger(__name__)


def _trim(messages: list, max_messages: int = 50) -> list:
    trimmed = messages[-max_messages:]
    for i, msg in enumerate(trimmed):
        if getattr(msg, "type", "") != "tool":
            return trimmed[i:]
    return trimmed


def _get_all_tools():
    agent_tools = get_agent_tool()
    skill_tools = get_skill_tools()
    return agent_tools + skill_tools


async def agent_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    activated_skills = state.get("activated_skills", [])
    skill_hint = state.get("skill_hint", "")

    logger.info(f"skill hint {skill_hint}")

    llm = get_llm()

    llm_with_tools = llm.bind_tools(_get_all_tools())

    if not skill_hint:
        system_content = "\n".join(
            [get_sys_prompt(), build_layer1_prompt(get_skill_registry())]
        )
    else:
        guide = state.get("guide")
        system_content = "\n".join(
            [get_sys_prompt(), build_layer2_prompt(skill_hint, guide)]
        )
    system_msg = SystemMessage(content=system_content)
    first_human = next((m for m in messages if getattr(m, "type", "") == "human"), None)
    recent = messages[-50:]
    if first_human and first_human not in recent:
        recent = [first_human] + recent[-49:]
    llm_messages = [system_msg] + recent

    print("messages数量", len(llm_messages))

    response = await llm_with_tools.ainvoke(llm_messages)

    for tc in response.tool_calls:
        if not tc.get("id"):
            tc["id"] = str(uuid.uuid4())

    print("===agent 节点执行结果", response)

    tcs = response.tool_calls
    if tcs and any(not tc.get("name", "") for tc in tcs):
        logger.error("Agent内部异常，tool name 为空", extra={"tool_calls": tcs})
        return {"messages": AIMessage(content=f"智能体内部异常")}

    if not response.content and not tcs:
        logger.warning("Agent返回空响应，尝试重新调用")
        retry_response = await llm_with_tools.ainvoke(llm_messages)
        for tc in retry_response.tool_calls:
            if not tc.get("id"):
                tc["id"] = str(uuid.uuid4())
        if not retry_response.content and not retry_response.tool_calls:
            return {
                "messages": AIMessage(
                    content="抱歉，我暂时无法生成有效的回复，请重新描述您的需求。"
                )
            }
        return {"messages": [retry_response], "activated_skills": activated_skills}

    return {
        "messages": [response],
        "activated_skills": activated_skills,
    }


async def _run_subagent_tool_loop(
    subagent_llm, subagent_tools: list, messages: list, initial_response
) -> str:
    """
    子智能体的工具调用循环（Claude Code CLI 的做法）。

    子智能体和主智能体一样，是完整的 agent loop：
        LLM → tool_call → 执行工具 → ToolMessage → LLM → ... → 纯文本

    不同之处：
    - 主智能体：循环由 LangGraph graph 驱动（agent_node ↔ tool_executor_node）
    - 子智能体：循环在 subagent_node 内部用 while 循环驱动
      （因为子智能体是临时创建的，不需要持久化到 graph）

    多轮工具调用的典型场景（以 grader 为例）：
      第 1 轮：read_file(transcript.md)    → 读取测试记录
      第 2 轮：list_directory(outputs/)     → 查看输出目录
      第 3 轮：read_file(output_1.json)     → 读取具体输出
      第 4 轮：纯文本，输出 grading.json    → 任务完成
    """
    current_messages = list(messages) + [initial_response]
    max_rounds = 10

    for _ in range(max_rounds):
        tool_calls = initial_response.tool_calls
        if not tool_calls:
            break

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool_id = tc.get("id", "")

            tool_func = next((t for t in subagent_tools if t.name == tool_name), None)

            if tool_func:
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, tool_func.invoke, tool_args
                    )
                except Exception as e:
                    result = f"Error: {e}"
            else:
                result = f"Unknown tool: {tool_name}"

            current_messages.append(
                ToolMessage(content=str(result), tool_call_id=tool_id, name=tool_name)
            )

        initial_response = await subagent_llm.ainvoke(current_messages)
        current_messages.append(initial_response)

        if not (
            hasattr(initial_response, "tool_calls") and initial_response.tool_calls
        ):
            break

    return initial_response.content


async def subagent_node(state: AgentState) -> dict:
    """
    子智能体节点：真正创建并执行子智能体。

    这是 Layer 3 的核心实现：
    1. 从 state.subagent_task 读取 agent_name 和 task_params
    2. 从 skill 的 agents/ 目录读取对应的 md 文件（grader.md / comparator.md / analyzer.md）
    3. 用该 md 内容作为子智能体的 system prompt
    4. 用 task_params 构造 user message
    5. 创建一个独立的 LLM 调用（子智能体）
    6. 子智能体执行完毕，结果作为 ToolMessage 返回主智能体

    这就是 Claude Code 中 "spawn a grader subagent" 的真正含义：
    不是在主智能体的上下文中执行，而是创建一个全新的 LLM 调用，
    用 agents/grader.md 定义它的角色和行为。
    """
    subagent_task = state.get("subagent_task")
    skill_hint = state.get("skill_hint")
    if not subagent_task:
        return {"messages": [], "subagent_task": None}

    agent_name = subagent_task.get("agent_name", "")
    md_path = subagent_task.get("md_path", "")
    task_params = subagent_task.get("task_params", {})
    tool_call_id = subagent_task.get("tool_call_id", "")

    skill_dir = Path(get_skill_registry().skills_dir).resolve() / skill_hint

    if not skill_dir.exists():
        return {
            "messages": [
                ToolMessage(
                    content="Error: No skill with agents/ directory found",
                    tool_call_id=tool_call_id,
                    name="spawn_subagent",
                )
            ],
            "subagent_task": None,
        }

    agent_prompt = load_bundled_resource(str(skill_dir), md_path)
    if not agent_prompt:
        return {
            "messages": [
                ToolMessage(
                    content=f"Error: agents/{agent_name}.md not found",
                    tool_call_id=tool_call_id,
                    name="spawn_subagent",
                )
            ],
            "subagent_task": None,
        }

    llm = get_llm()

    subagent_tools = _get_all_tools()
    subagent_llm = llm.bind_tools(subagent_tools)

    subagent_messages = [
        SystemMessage(content=agent_prompt),
        HumanMessage(content=json.dumps(task_params, ensure_ascii=False, indent=2)),
    ]

    try:
        subagent_response = await subagent_llm.ainvoke(subagent_messages)
        if hasattr(subagent_response, "tool_calls") and subagent_response.tool_calls:
            result = await _run_subagent_tool_loop(
                subagent_llm, subagent_tools, subagent_messages, subagent_response
            )
        else:
            result = subagent_response.content
    except Exception as e:
        result = f"Sub-agent execution error: {e}"

    return {
        "messages": [
            ToolMessage(
                content=result,
                tool_call_id=tool_call_id,
                name=f"spawn_subagent_{agent_name}",
            )
        ],
        "subagent_task": None,
    }


async def tool_executor_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    guide = state.get("guide", None)
    pending = state.get("pending_confirm")
    skill_hint = state.get("skill_hint", "")

    if pending and pending.get("approved"):
        logger.info("执行确认后的tool调用", tool_name=pending["tool_name"])
        tool_args = pending["tool_args"]
        tool_args["user_confirmed"] = True
        try:
            result = await execute_tool_call(
                pending["tool_name"], _get_all_tools(), tool_args
            )
            tool_msg = ToolMessage(
                content=str(result),
                tool_call_id=pending["tool_id"],
                name=pending["tool_name"],
            )
        except Exception as e:
            tool_msg = ToolMessage(
                content=f"Error after confirmation: {str(e)}",
                tool_call_id=pending["tool_id"],
                name=pending["tool_name"],
            )
        return {"messages": [tool_msg], "pending_confirm": None}

    if not messages:
        return {"messages": [], "pending_confirm": None}

    last_message = messages[-1]
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": [], "pending_confirm": None}

    new_messages = []
    hitl_triggered = None

    for tc in last_message.tool_calls:
        tool_name = tc.get("name", "")
        tool_args = tc.get("args", {})
        tool_id = tc.get("id", "")
        logger.info("执行tool调用", tool_name=tool_name)

        if tool_name == "spawn_subagent":
            subagent_task = {
                "agent_name": tool_args.get("agent_name", ""),
                "task_params": json.loads(tool_args.get("task_params_json", "{}")),
                "tool_call_id": tool_id,
            }
            new_messages.append(
                ToolMessage(
                    content=f"[子智能体 {subagent_task['agent_name']} 已创建，正在执行...]",
                    tool_call_id=tool_id,
                    name="spawn_subagent",
                )
            )
            continue

        try:
            result = await execute_tool_call(tool_name, _get_all_tools(), tool_args)
            result = str(result)
            if tool_name == "load_skill_guide":
                skill_hint = tool_args.get("skill_name", "")
                guide = result
                new_messages.append(
                    ToolMessage(
                        content=f"已获取skill完整指令",
                        tool_call_id=tool_id,
                        name="spawn_subagent",
                    )
                )
                continue

            logger.info("执行tool结果", result=result)
            tool_msg = ToolMessage(
                content=result,
                tool_call_id=tool_id,
                name=tool_name,
            )
        except HITLRequiredError as e:
            logger.info("触发用户确认中断", tool_name=tool_name)
            interrupt_id = str(uuid.uuid4())
            if hitl_triggered is None:
                hitl_triggered = {
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "tool_id": tool_id,
                    "action": e.action,
                    "message": e.message,
                    "approved": False,
                    "type": e.type,
                    "interrupt_id": interrupt_id,
                }
            tool_msg = ToolMessage(
                content=f"[HITL_REQUIRED] {e.message}",
                tool_call_id=tool_id,
                name=tool_name,
            )
        except SecurityError as e:
            logger.error("执行工具时报安全错误", tool_name=tool_name, error=e.message)
            raise
            tool_msg = ToolMessage(
                content=f"Security Error: {e.message}",
                tool_call_id=tool_id,
                name=tool_name,
            )
        except Exception as e:
            logger.error("执行工具时报异常", tool_name=tool_name, error=str(e))
            import traceback

            traceback.print_exc()
            raise
            tool_msg = ToolMessage(
                content=f"Error executing tool {tool_name}: {str(e)}",
                tool_call_id=tool_id,
                name=tool_name,
            )

        new_messages.append(tool_msg)

    if hitl_triggered:
        return {
            "pending_confirm": hitl_triggered,
            "messages": new_messages,
            "skill_hint": skill_hint,
            "guide": guide,
        }

    result = {
        "messages": new_messages,
        "pending_confirm": None,
        "skill_hint": skill_hint,
        "guide": guide,
    }

    return result


def human_confirm_node(state: AgentState) -> dict:
    pending = state.get("pending_confirm")
    interrupt_id = pending.get("interrupt_id", "")

    confirm_data = {
        "type": pending.get("type", ""),
        "action": pending.get("action", ""),
        "message": pending.get("message", "确认执行此操作?"),
        "interrupt_id": interrupt_id,
    }
    try:
        print("是不是需要用户确认了？？？？？？？？？？？？？", confirm_data)
        decision = interrupt(confirm_data)
        print("用户确认了吗？？？？？？？？？？？", decision)

        return {
            "messages": [
                HumanMessage(content=f"[用户确认信息] {decision.get(interrupt_id, '')}")
            ],
            "pending_confirm": None,
        }
    except GraphInterrupt:
        raise  # 重新抛出，让LangGraph框架处理
    except Exception as e:
        # 处理其他非GraphInterrupt的业务异常
        print("用户确认的时候报错了", e)
        # 返回一个错误 ToolMessage，避免异常逃逸
        return {
            "messages": [
                ToolMessage(
                    content=f"确认流程出错: {str(e)}",
                    tool_call_id=pending.get("tool_id", "unknown"),
                )
            ]
        }


def should_use_tools(state: AgentState) -> str:
    messages = state.get("messages", [])
    pending = state.get("pending_confirm")
    if not messages:
        return "end"
    last_message = messages[-1]

    if pending:
        logger.info("走到human_confirm节点")
        return "human_confirm"

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        logger.info("走到tools节点")
        return "tools"
    logger.info("走到end节点", res="end")
    return "end"


def route_tools(state: AgentState) -> str:
    subagent_task = state.get("subagent_task")
    if subagent_task:
        logger.info("走到subagent节点")
        return "subagent"
    pending = state.get("pending_confirm")
    if pending and not pending.get("approved"):
        logger.info("走到human_confirm节点")
        return "human_confirm"
    logger.info("走到agent节点")
    return "agent"


def route_after_confirm(state: AgentState) -> str:
    pending = state.get("pending_confirm")
    if pending and pending.get("approved"):
        logger.info("用户确认后执行什么", res="tools")
        return "tools"
    logger.info("用户确认后执行什么", res="agent")
    return "agent"
