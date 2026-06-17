import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.config import get_settings
from app.security.shell_guard import validate_command
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SandboxResult:
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""


async def execute_script(script_path: str, args: dict | None = None, cwd: str | None = None) -> SandboxResult:
    settings = get_settings()
    result = SandboxResult()

    resolved_script = Path(script_path).resolve()
    if not resolved_script.exists():
        result.stderr = f"Script not found: {script_path}"
        return result

    work_dir = cwd or str(resolved_script.parent)

    try:
        proc = await asyncio.create_subprocess_exec(
            "python", str(resolved_script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )

        stdin_data = json.dumps(args or {}).encode("utf-8")
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=settings.agent.SANDBOX_TIMEOUT_SECONDS,
            )
            result.exit_code = proc.returncode or 0
            result.stdout = stdout.decode("utf-8", errors="replace")
            result.stderr = stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.exit_code = -1
            result.stderr = f"Script execution timed out after {settings.agent.SANDBOX_TIMEOUT_SECONDS}s"
            logger.warning("script_timeout", script_path=script_path)
    except Exception as e:
        result.stderr = str(e)
        logger.error("script_execution_error", script_path=script_path, error=str(e))

    return result


async def execute_sandboxed(command: str, args: list[str] | None = None, cwd: str | None = None) -> SandboxResult:
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
                timeout=settings.agent.SANDBOX_TIMEOUT_SECONDS,
            )
            result.exit_code = proc.returncode or 0
            result.stdout = stdout.decode("utf-8", errors="replace")
            result.stderr = stderr.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            result.exit_code = -1
            result.stderr = f"Command timed out after {settings.agent.SANDBOX_TIMEOUT_SECONDS}s"
    except Exception as e:
        result.stderr = str(e)

    return result
