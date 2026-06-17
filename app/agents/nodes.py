from app.agents.state import AgentState
from app.security.path_validator import validate_path, HITLRequiredError, SecurityError
from app.security.shell_guard import validate_command
from app.tools.sandbox import execute_sandboxed


async def plan_node(state: AgentState) -> dict:
    messages = state.get("messages", [])
    user_message = messages[-1] if messages else {}
    content = user_message.get("content", "") if isinstance(user_message, dict) else str(user_message)

    skill_hint = state.get("skill_hint")

    plan = f"Process user request: {content[:200]}"
    if skill_hint:
        plan = f"Use skill '{skill_hint}' to handle: {content[:200]}"

    return {"current_plan": plan, "hitl_required": False, "hitl_context": None, "error": None}


async def execute_node(state: AgentState) -> dict:
    plan = state.get("current_plan", "")
    tool_results = []

    try:
        return {
            "tool_results": tool_results,
            "hitl_required": False,
            "hitl_context": None,
            "error": None,
        }
    except HITLRequiredError as e:
        return {
            "hitl_required": True,
            "hitl_context": {
                "action": e.action,
                "message": e.message,
                **e.context,
            },
            "error": None,
        }
    except SecurityError as e:
        return {"hitl_required": False, "error": e.message}
    except Exception as e:
        return {"hitl_required": False, "error": str(e)}


async def summarize_node(state: AgentState) -> dict:
    tool_results = state.get("tool_results", [])
    error = state.get("error")

    if error:
        return {"messages": state.get("messages", []) + [{"role": "assistant", "content": f"Error: {error}"}]}

    summary = "Task completed successfully."
    if tool_results:
        summary = f"Task completed. Results: {len(tool_results)} operation(s) performed."

    return {"messages": state.get("messages", []) + [{"role": "assistant", "content": summary}]}


async def human_interrupt_node(state: AgentState) -> dict:
    return state


def should_interrupt(state: AgentState) -> bool:
    return state.get("hitl_required", False)


def should_replan(state: AgentState) -> bool:
    return bool(state.get("error"))
