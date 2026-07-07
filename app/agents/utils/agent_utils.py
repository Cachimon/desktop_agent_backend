from pathlib import Path

from app.utils.exceptions import HITLRequiredError
from app.utils.logging import get_logger

logger = get_logger(__name__)

def load_bundled_resource(skill_dir: str, resource_path: str) -> str | None:
    """
    Layer 3: 从 skill 的 bundled resources 中按需读取文件。

    这是三层加载中最轻量的一层：
    - agents/  下的 .md 文件：作为子智能体的 system prompt
    - references/ 下的 .md 文件：作为参考文档注入当前 prompt
    - scripts/ 下的 .py 文件：直接执行，不需要加载到 prompt
    - assets/ 下的文件：模板等静态资源

    关键区别：
    - Layer 1 和 Layer 2 是自动注入 system prompt 的
    - Layer 3 是主智能体在执行过程中 **主动读取** 的
      读取后有两种用法：
      1. 作为子智能体（subagent）的 system prompt → spawn 新 agent
      2. 作为参考文档追加到当前 prompt
    """
    full_path = Path(skill_dir).resolve() / resource_path
    if not full_path.exists():
        return None
    return full_path.read_text(encoding="utf-8", errors="replace")

async def execute_tool_call(tool_name: str, all_tools, tool_args: dict[str, Any]) -> str:
    tool_map = {t.name: t for t in all_tools}

    if tool_name not in tool_map:
        logger.warning("unknown_tool_called", tool_name=tool_name)
        return f"Error: Unknown tool '{tool_name}'"

    tool = tool_map[tool_name]
    try:
        result = await tool.ainvoke(tool_args)
        return str(result)
    except HITLRequiredError:
        raise
    except Exception as e:
        logger.error("tool_execution_error", tool_name=tool_name, error=str(e))
        return f"Error executing {tool_name}: {str(e)}"
