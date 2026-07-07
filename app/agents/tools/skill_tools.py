import json
import subprocess
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agents.utils.prompt_utils import load_skill_instructions
from app.services.skill_service import get_skill_registry
from app.utils.logging import get_logger

logger = get_logger(__name__)

class ExecuteSkillScriptInput(BaseModel):
    skill_name: str = Field(
        description="Name of the skill that owns the script (e.g. file-manager)"
    )
    script_name: str = Field(description="Script filename to execute (e.g. renamer.py)")
    args: str = Field(
        description='传给脚本的参数的json格式',
    )
    timeout: int = Field(default=30, description="执行超时时间（秒）")

@tool(
    description="执行脚本的工具",
    args_schema=ExecuteSkillScriptInput,
)
def execute_skill_script(
    skill_name: str,
    script_name: str | None = None,  # 新增：指定脚本名
    args: str = "",
    timeout: int = 30,
) -> dict:
    """
    执行 skill 关联的脚本。

    返回:
      {"success": bool, "stdout": str, "stderr": str, "exit_code": int}
    """
    registry = get_skill_registry()
    if skill_name not in registry.skills:
        logger.error(f"没找到Skill【{skill_name}】")
        raise
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Skill '{skill_name}' not found",
            "exit_code": -1,
        }

    entry = registry.skills[skill_name]
    if not entry.scripts:
        logger.error(f"Skill【{skill_name}】没有脚本")
        raise
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Skill '{skill_name}' has no scripts",
            "exit_code": -1,
        }

    if script_name not in entry.scripts:
        logger.error(f"脚本【{script_name}】没找到")
        raise
        return {
            "success": False,
            "stdout": "",
            "stderr": f"脚本 '{script_name}' 没找到",
            "exit_code": -1,
        }

    scripts_dir = Path(entry.skill_dir).resolve() / "scripts"
    script_path = scripts_dir / script_name

    if not script_path.exists():
        logger.error(f"脚本路径【{script_path}】没找到")
        raise
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script not found: {script_path}",
            "exit_code": -1,
        }

    try:
        stdin_data = args
        proc = subprocess.run(
            ["python", str(script_path)],
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(scripts_dir),
        )
        if proc.returncode != 0:
            logger.error(f"执行脚本【{script_name}】异常：{proc.returncode}【{proc.stderr}】")
            raise
        return {
            "success": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        logger.error(f"执行脚本【{script_name}】超时了")
        raise
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script timed out after {timeout}s",
            "exit_code": -1,
        }
    except Exception as e:
        logger.error(f"执行脚本【{script_name}】异常了", error=str(e))
        raise
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}



class SpawnSubagentInput(BaseModel):
    agent_name: str = Field(
        description="子智能体名称，用md文件的去掉后缀的文件名"
    )
    md_path: str = Field(
        description="作为子智能体system prompt的md文件相对于skill的位置，一般直接在skill中获取即可"
    )
    task_params_json: str = Field(description="任务参数 JSON")
@tool(
    description="spawn 一个子智能体执行任务。会读取 skill 下的 md 作为子智能体 system prompt，创建独立的 LLM 调用来执行。",
    args_schema=SpawnSubagentInput,
)
def spawn_subagent(agent_name: str, md_path: str, task_params_json: str) -> str:
    return json.dumps(
        {
            "action": "spawn_subagent",
            "agent_name": agent_name,
            "md_path": md_path,
            "task_params": json.loads(task_params_json),
        },
        ensure_ascii=False,
    )


class LoadSkillGuideInput(BaseModel):
    skill_name: str = Field(description="要加载的 skill 名称")

@tool(
    description="加载指定 skill 的完整指令或指令。当用户需求匹配某个 skill 时调用此工具，将 skill 的完整 instructions 注入上下文。",
    args_schema=LoadSkillGuideInput,
)
def load_skill_guide(skill_name: str) -> str:
    instructions = load_skill_instructions(get_skill_registry(), skill_name)
    return instructions

def get_skill_tools():

    return [
        execute_skill_script,
        spawn_subagent,
        load_skill_guide,
    ]

