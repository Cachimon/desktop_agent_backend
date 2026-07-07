import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.security.shell_guard import validate_command
from app.utils.logging import get_logger

logger = get_logger(__name__)


# Windows 子进程支持：确保事件循环支持子进程创建
def _ensure_proactor_loop():
    if sys.platform == "win32":
        loop = asyncio.get_event_loop()
        if not isinstance(loop, asyncio.ProactorEventLoop):
            logger.info("所以事件循环不是ProactorEventLoop")
            policy = asyncio.WindowsProactorEventLoopPolicy()
            loop = policy.get_event_loop()
            asyncio.set_event_loop(loop)
    return asyncio.get_event_loop()


@dataclass
class SandboxResult:
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""


async def execute_script(
    script_path: str, args: dict | None = None, cwd: str | None = None
) -> SandboxResult:
    _ensure_proactor_loop()
    settings = get_settings()
    result = SandboxResult()

    resolved_script = Path(script_path).resolve()
    if not resolved_script.exists():
        result.stderr = f"Script not found: {script_path}"
        return result

    work_dir = cwd or str(resolved_script.parent)

    try:
        # 不可用asyncio.create_subprocess_exec
        proc = subprocess.run(
            r"python str(resolved_script)",
            shell=True,  # 会让 subprocess.run 自动调用 cmd.exe，且正确处理引号嵌套
            capture_output=True,
            timeout=30,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,  # 明确设置 stdin，让 input() 立刻抛 EOFError
        )

        logger.info("脚本执行完毕", script_path=script_path)

        stdin_data = json.dumps(args or {}).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=settings.agent_cfg.SANDBOX_TIMEOUT_SECONDS,
            )
            result.exit_code = proc.returncode or 0
            result.stdout = stdout.decode("utf-8", errors="replace")
            result.stderr = stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.exit_code = -1
            result.stderr = f"Script execution timed out after {settings.agent_cfg.SANDBOX_TIMEOUT_SECONDS}s"
            logger.warning("script_timeout", script_path=script_path)
    except Exception as e:
        import traceback

        traceback.print_exc()
        result.stderr = str(e)
        logger.error("script_execution_error", script_path=script_path, error=str(e))

    return result


async def execute_sandboxed(
    command: str, args: list[str] | None = None, cwd: str | None = None
) -> SandboxResult:
    _ensure_proactor_loop()
    validate_command(command)

    settings = get_settings()
    result = SandboxResult()

    cmd_parts = [command] + (args or [])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=settings.agent_cfg.SANDBOX_TIMEOUT_SECONDS,
            )
            result.exit_code = proc.returncode or 0
            result.stdout = stdout.decode("utf-8", errors="replace")
            result.stderr = stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.exit_code = -1
            result.stderr = (
                f"Command timed out after {settings.agent_cfg.SANDBOX_TIMEOUT_SECONDS}s"
            )
    except Exception as e:
        result.stderr = str(e)

    return result
