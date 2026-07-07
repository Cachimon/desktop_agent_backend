import asyncio
import fnmatch
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.security.shell_guard import validate_command, WORKSPACE_DIR
from app.utils.exceptions import HITLRequiredError
from app.utils.logging import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_DESTRUCTIVE_COMMANDS = {"mv", "ren", "del", "rm", "cp", "copy", "xcopy", "rmdir"}


def _is_destructive_command(command: str) -> bool:
    stripped = command.strip().lower()
    first_token = stripped.split()[0] if stripped.split() else ""
    if first_token in _DESTRUCTIVE_COMMANDS:
        return True
    if first_token in ("python", "node") and (
        "rename" in stripped
        or "move" in stripped
        or "shutil" in stripped
        or "os.remove" in stripped
        or "os.replace" in stripped
    ):
        return True
    return False


def _validate_path_sync(file_path: str, operation: str = "read") -> Path:
    resolved = Path(file_path).resolve()
    try:
        if resolved.is_relative_to(_PROJECT_ROOT):
            return resolved
    except OSError, ValueError:
        pass

    if not resolved.exists() and operation == "write":
        try:
            if resolved.parent.is_relative_to(_PROJECT_ROOT):
                return resolved
        except OSError, ValueError:
            pass

    return resolved


# ==================== Read ====================


class ReadFileInput(BaseModel):
    file_path: str = Field(description="要读取的文件的绝对路径")
    offset: int = Field(default=1, description="起始行号（1-indexed）")
    limit: int = Field(default=2000, description="最多读取的行数")


@tool(
    description="读取文件内容，返回带行号的文本。用于检查现有文件、理解代码结构。编辑文件前应先读取了解上下文。",
    args_schema=ReadFileInput,
)
def read_file(file_path: str, offset: int = 1, limit: int = 2000):
    resolved = _validate_path_sync(file_path, operation="read")

    if not resolved.exists():
        return f"Error: File not found: {file_path}"
    if not resolved.is_file():
        return f"Error: Not a file: {file_path}"

    try:
        lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines()
        selected = lines[offset - 1 : offset - 1 + limit]
        numbered = [f"{i + offset}: {line}" for i, line in enumerate(selected)]
        result = "\n".join(numbered)
        if offset + limit - 1 < len(lines):
            result += f"\n... ({len(lines) - offset - limit + 1} more lines)"
        return result
    except Exception as e:
        return f"Error reading file: {e}"


# ==================== Write ====================


class WriteFileInput(BaseModel):
    file_path: str = Field(description="要写入的文件的绝对路径")
    content: str = Field(description="要写入的文件内容")


@tool(
    description="将内容写入文件，如果文件不存在则创建（包括父目录）。用于创建新文件或完全覆盖已有文件。",
    args_schema=WriteFileInput,
)
def write_file(file_path: str, content: str):
    resolved = _validate_path_sync(file_path, operation="write")

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        logger.info("file_written", path=str(resolved), size=len(content))
        return f"Successfully wrote {len(content)} characters to {resolved}"
    except Exception as e:
        return f"Error writing file: {e}"


# ==================== Edit ====================


class EditFileInput(BaseModel):
    file_path: str = Field(description="要编辑的文件的绝对路径")
    old_string: str = Field(description="要替换的原始文本，必须完全匹配")
    new_string: str = Field(description="替换后的新文本")
    replace_all: bool = Field(default=False, description="是否替换所有匹配项")


@tool(
    description="对文件进行精确字符串替换编辑。old_string 必须与文件内容完全匹配。用于针对性编辑而非重写整个文件。",
    args_schema=EditFileInput,
)
def edit_file(
    file_path: str, old_string: str, new_string: str, replace_all: bool = False
):
    resolved = _validate_path_sync(file_path, operation="write")

    if not resolved.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"

    count = content.count(old_string)
    if count == 0:
        return "Error: old_string not found in file"
    if count > 1 and not replace_all:
        return f"Error: Found {count} matches for old_string. Use replace_all=true to replace all, or provide more context to make the match unique."

    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)

    try:
        resolved.write_text(new_content, encoding="utf-8")
        replaced = count if replace_all else 1
        logger.info("file_edited", path=str(resolved), replacements=replaced)
        return f"Successfully replaced {replaced} occurrence(s) in {resolved}"
    except Exception as e:
        return f"Error writing file: {e}"


# ==================== MultiEdit ====================


class MultiEditInput(BaseModel):
    file_path: str = Field(description="要编辑的文件的绝对路径")
    edits: list[dict] = Field(
        description=(
            "编辑操作列表，每个字典包含：\n"
            "- old_string: 要替换的原始文本（必填）\n"
            "- new_string: 替换后的新文本（必填）\n"
            "- replace_all: 是否替换所有匹配，默认 False（可选）"
        )
    )


@tool(
    description="对同一文件执行多处精确字符串替换编辑。比多次调用 edit_file 更高效，所有编辑在一次性写入前验证。",
    args_schema=MultiEditInput,
)
def multi_edit(file_path: str, edits: list[dict]):
    resolved = _validate_path_sync(file_path, operation="write")
    if not resolved.exists():
        return f"Error: File not found: {file_path}"

    try:
        content = resolved.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"

    errors = []
    for i, edit_op in enumerate(edits):
        old_string = edit_op.get("old_string", "")
        new_string = edit_op.get("new_string", "")
        replace_all = edit_op.get("replace_all", False)

        count = content.count(old_string)
        if count == 0:
            errors.append(f"Edit {i}: old_string not found")
            continue
        if count > 1 and not replace_all:
            errors.append(
                f"Edit {i}: found {count} matches, use replace_all=true or provide more context"
            )
            continue

        if replace_all:
            content = content.replace(old_string, new_string)
        else:
            content = content.replace(old_string, new_string, 1)

    if errors:
        return "Errors:\n" + "\n".join(errors)

    try:
        resolved.write_text(content, encoding="utf-8")
        return f"Successfully applied {len(edits)} edit(s) to {resolved}"
    except Exception as e:
        return f"Error writing file: {e}"


# ==================== Bash ====================


class BashInput(BaseModel):
    command: str = Field(description="要执行的 shell 命令")
    timeout: int = Field(default=30, description="超时时间（秒）")


@tool(
    description=(
        "执行 shell 命令。仅允许白名单内的命令。"
        "对于破坏性命令（mv, ren, del, rm, cp 等），应先执行只读预览命令查看变更，再执行实际操作。"
    ),
    args_schema=BashInput,
)
async def bash(command: str, timeout: int = 30) -> str:
    """
    在物理隔离的沙盒环境中执行 Bash 命令。
    严格限制破坏性操作，并强制将文件操作重定向到更安全的专用工具。
    """
    # 1. 安全校验
    error_msg = validate_command(command)
    if error_msg:
        return error_msg

    # 2. 定义底层同步执行逻辑
    def _run():
        try:
            # 统一使用 shell=True 并传入完整字符串，避免 split() 导致的引号解析问题
            # text=True 等同于 universal_newlines=True，自动处理解码
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,  # 防止程序等待标准输入挂起
                cwd=WORKSPACE_DIR  # 强制将工作区作为命令执行的起始目录
            )

            output = proc.stdout
            if proc.stderr:
                output += f"\nSTDERR:\n{proc.stderr}"
            if proc.returncode and proc.returncode != 0:
                output += f"\nExit code: {proc.returncode}"

            return output.strip() or "(no output)"

        except subprocess.TimeoutExpired:
            return f"⏰ Error: 命令执行超时（超过 {timeout} 秒），可能陷入了死循环或等待输入。"
        except Exception as e:
            return f"❌ Error executing command: {type(e).__name__} - {e}"

    # 3. 异步执行，避免阻塞 FastAPI 主线程
    try:
        result = await asyncio.to_thread(_run)
        return result
    except Exception as e:
        return f"❌ System Error: {e}"


async def _bash(command: str, timeout: int = 30):
    try:
        validate_command(command)
    except Exception as e:
        return f"Error: {e}"

    if _is_destructive_command(command):
        return f"Error: Destructive command detected. Please use move_file/copy_file/delete_file tools instead, or confirm with preview first."

    import platform

    is_windows = platform.system() == "Windows"

    def _run():
        if is_windows:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        else:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        output = proc.stdout.decode("utf-8", errors="replace")
        if proc.stderr:
            output += f"\nSTDERR:\n{proc.stderr.decode('utf-8', errors='replace')}"
        if proc.returncode and proc.returncode != 0:
            output += f"\nExit code: {proc.returncode}"
        return output or "(no output)"

    try:
        return await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s"
    except Exception as e:
        return f"Error executing command: {type(e).__name__} {e}"


# ==================== Glob ====================


class GlobInput(BaseModel):
    pattern: str = Field(description="Glob 匹配模式（如 **/*.py, *.md）")
    path: str = Field(default=".", description="要搜索的目录路径")


def _glob_match(pattern: str, path: str) -> bool:
    if "**" in pattern:
        return fnmatch.fnmatch(path, pattern)
    return fnmatch.fnmatch(path, pattern)


@tool(
    description="按 glob 模式搜索文件（如 **/*.py, *.md）。返回匹配的文件路径列表。",
    args_schema=GlobInput,
)
def glob_search(pattern: str, path: str = "."):
    resolved = _validate_path_sync(path, operation="read")

    if not resolved.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        matches = []
        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for filename in files:
                if fnmatch.fnmatch(
                    filename,
                    pattern.strip("*").split("/")[-1] if "/" in pattern else pattern,
                ):
                    full_path = Path(root).resolve() / filename
                    rel = str(full_path.relative_to(resolved))
                    if _glob_match(pattern, rel):
                        matches.append(str(full_path))

        matches.sort()
        if not matches:
            return "No files found matching pattern"
        return "\n".join(matches[:100]) + (
            f"\n... and {len(matches) - 100} more" if len(matches) > 100 else ""
        )
    except Exception as e:
        return f"Error searching files: {e}"


# ==================== Grep ====================


class GrepInput(BaseModel):
    pattern: str = Field(description="正则表达式搜索模式")
    path: str = Field(default=".", description="要搜索的目录路径")
    include: str | None = Field(default=None, description="文件名过滤模式（如 *.py）")


@tool(
    description="使用正则表达式搜索文件内容。返回匹配的文件路径、行号和内容。",
    args_schema=GrepInput,
)
def grep_search(pattern: str, path: str = ".", include: str | None = None):
    resolved = _validate_path_sync(path, operation="read")

    if not resolved.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return f"Error: Invalid regex pattern: {e}"

    try:
        results = []
        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]
            for filename in files:
                if include and not fnmatch.fnmatch(filename, include):
                    continue
                filepath = Path(root).resolve() / filename
                try:
                    text = filepath.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            rel = str(filepath.relative_to(resolved))
                            results.append(f"{rel}:{i}: {line.strip()}")
                            if len(results) >= 50:
                                return (
                                    "\n".join(results)
                                    + "\n... (truncated, more matches exist)"
                                )
                except OSError, PermissionError:
                    continue

        if not results:
            return "No matches found"
        return "\n".join(results)
    except Exception as e:
        return f"Error searching: {e}"


# ==================== ListDirectory ====================


class ListDirectoryInput(BaseModel):
    path: str = Field(description="要列出的目录的绝对路径")
    deep: bool = Field(default=False, description="是否递归列出子目录内容")


@tool(
    description="列出指定目录下的文件和子目录，类似于 ls 命令。返回目录结构概览，包含文件名、子目录名及基本类型标识。",
    args_schema=ListDirectoryInput,
)
def list_directory(path: str, deep: bool = False):
    resolved = Path(path).resolve()
    if not resolved.exists():
        return f"Error: Path not found: {path}"
    if not resolved.is_dir():
        return f"Error: Not a directory: {path}"

    try:
        entries = sorted(
            resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
        )
        lines = []
        for entry in entries:
            if entry.is_dir():
                lines.append(f"{entry.name}/")
            else:
                size = entry.stat().st_size
                lines.append(f"{entry.name}  ({size} bytes)")

        if deep:
            sub_results = []
            for entry in resolved.iterdir():
                if (
                    entry.is_dir()
                    and not entry.name.startswith(".")
                    and entry.name != "__pycache__"
                ):
                    sub_result = list_directory(str(entry), deep=True)
                    sub_results.append(
                        f"\n  [{entry.name}/]\n  " + sub_result.replace("\n", "\n  ")
                    )
            if sub_results:
                lines.extend(sub_results)

        return "\n".join(lines)
    except PermissionError:
        return f"Error: Permission denied: {path}"
    except Exception as e:
        return f"Error listing directory: {e}"


# ==================== WebFetch ====================


class WebFetchInput(BaseModel):
    url: str = Field(description="要获取内容的网页 URL")
    format: str = Field(default="text", description="返回格式：text 或 markdown")
    timeout: int = Field(default=30, description="请求超时时间（秒）")


@tool(
    description="获取指定 URL 的网页内容，支持返回纯文本或 Markdown 格式。用于读取网页、API 文档等在线资源。",
    args_schema=WebFetchInput,
)
def web_fetch(url: str, format: str = "text", timeout: int = 30):
    try:
        import httpx
    except ImportError:
        return "Error: httpx is not installed. Run: pip install httpx"

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "")

            if "json" in content_type:
                try:
                    return json.dumps(resp.json(), ensure_ascii=False, indent=2)
                except Exception:
                    return resp.text

            text = resp.text

            if format == "markdown":
                try:
                    import markdownify

                    return markdownify.markdownify(text)
                except ImportError:
                    return text

            return text
    except httpx.TimeoutException:
        return f"Error: Request timed out after {timeout}s"
    except httpx.HTTPStatusError as e:
        return f"Error: HTTP {e.response.status_code} - {e.response.reason_phrase}"
    except Exception as e:
        return f"Error fetching URL: {e}"


# ==================== WebSearch ====================


class WebSearchInput(BaseModel):
    query: str = Field(description="搜索关键词")
    max_results: int = Field(default=5, description="最大返回结果数")


@tool(
    description="使用搜索引擎搜索互联网信息，返回相关结果的标题、链接和摘要。用于查找文档、解决方案、最新资讯等。",
    args_schema=WebSearchInput,
)
def web_search(query: str, max_results: int = 5):
    try:
        import httpx
    except ImportError:
        return "Error: httpx is not installed. Run: pip install httpx"

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            abstract = data.get("Abstract")
            if abstract:
                results.append(
                    {
                        "title": data.get("Heading", ""),
                        "url": data.get("AbstractURL", ""),
                        "snippet": abstract,
                    }
                )

            for topic in data.get("RelatedTopics", []):
                if isinstance(topic, dict) and "Text" in topic:
                    results.append(
                        {
                            "title": topic.get("Text", "")[:80],
                            "url": topic.get("FirstURL", ""),
                            "snippet": topic.get("Text", ""),
                        }
                    )
                if len(results) >= max_results:
                    break

            if not results:
                return f"No results found for: {query}"

            return json.dumps(results[:max_results], ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error searching: {e}"


# ==================== AskUser ====================


class AskUserInput(BaseModel):
    question: str = Field(description="要向用户提出的问题")
    options: str= Field(
        default="[]", description="list[str]结构的json字符串，可选的选项列表，供用户选择"
    )


@tool(
    description="向用户提问以获取信息或确认操作。当智能体需要用户输入、决策或确认时使用此工具。",
    args_schema=AskUserInput,
)
def ask_user(question: str, options: str = "[]"):
    _options = json.loads(options)
    if _options:
        options_text = "\n".join(f"  {i + 1}. {opt}" for i, opt in enumerate(_options))
        raise HITLRequiredError(
            action="ask_user",
            message=f"{question}\n\n可选选项：\n{options_text}",
            context={"question": question, "options": _options},
        )
    raise HITLRequiredError(
        action="ask_user",
        message=question,
        context={"question": question},
    )


# ==================== TodoWrite ====================


class TodoWriteInput(BaseModel):
    todos: list[dict] = Field(
        description=(
            "任务列表，每个任务是一个字典，包含以下字段：\n"
            "- content: 任务描述（必填）\n"
            "- status: 任务状态，可选值为 pending/in_progress/completed/cancelled（必填）\n"
            "- priority: 优先级，可选值为 high/medium/low（必填）"
        )
    )


_todo_store: list[dict] = []


@tool(
    description="创建或更新任务列表。用于跟踪多步骤任务的进度，帮助用户了解当前工作状态。",
    args_schema=TodoWriteInput,
)
def todo_write(todos: list[dict]):
    global _todo_store
    _todo_store = todos
    lines = []
    for todo in todos:
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }.get(todo.get("status", "pending"), "[ ]")
        priority = todo.get("priority", "medium")
        content = todo.get("content", "")
        lines.append(f"  {status_icon} ({priority}) {content}")
    return "任务列表已更新：\n" + "\n".join(lines)


# ==================== TodoRead ====================


class TodoReadInput(BaseModel):
    pass


@tool(
    description="读取当前任务列表，查看所有任务的状态和进度。",
    args_schema=TodoReadInput,
)
def todo_read():
    if not _todo_store:
        return "当前没有任务"
    lines = []
    for todo in _todo_store:
        status_icon = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }.get(todo.get("status", "pending"), "[ ]")
        priority = todo.get("priority", "medium")
        content = todo.get("content", "")
        lines.append(f"  {status_icon} ({priority}) {content}")
    return "当前任务列表：\n" + "\n".join(lines)


# ==================== NotebookRead ====================


class NotebookReadInput(BaseModel):
    file_path: str = Field(description="Jupyter notebook 文件的绝对路径")
    cell_start: int = Field(default=0, description="起始 cell 索引（0-indexed）")
    cell_end: int | None = Field(
        default=None, description="结束 cell 索引（不包含），None 表示到末尾"
    )


@tool(
    description="读取 Jupyter notebook (.ipynb) 文件的内容，返回指定范围内的 cell 信息，包括 cell 类型、源代码和输出。",
    args_schema=NotebookReadInput,
)
def notebook_read(file_path: str, cell_start: int = 0, cell_end: int | None = None):
    try:
        import nbformat
    except ImportError:
        return "Error: nbformat is not installed. Run: pip install nbformat"

    resolved = Path(file_path).resolve()
    if not resolved.exists():
        return f"Error: File not found: {file_path}"

    try:
        nb = nbformat.read(str(resolved), as_version=4)
        cells = nb.cells[cell_start:cell_end]
        results = []
        for i, cell in enumerate(cells):
            cell_index = cell_start + i
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", "")
            results.append(f"[Cell {cell_index}] type={cell_type}\n{source}")

            outputs = cell.get("outputs", [])
            for out in outputs:
                if out.get("output_type") == "stream":
                    results.append(f"  Output:\n{out.get('text', '')}")
                elif out.get("output_type") == "error":
                    results.append(f"  Error:\n{''.join(out.get('traceback', []))}")
                elif "data" in out:
                    for mime, content in out["data"].items():
                        if mime == "text/plain":
                            results.append(f"  Output:\n{content}")

        return "\n\n".join(results)
    except Exception as e:
        return f"Error reading notebook: {e}"


# ==================== NotebookEdit ====================


class NotebookEditInput(BaseModel):
    file_path: str = Field(description="Jupyter notebook 文件的绝对路径")
    cell_index: int = Field(description="要编辑的 cell 索引（0-indexed）")
    new_source: str = Field(description="新的 cell 源代码内容")
    cell_type: str | None = Field(
        default=None, description="新的 cell 类型：code 或 markdown，None 表示保持不变"
    )
    new_cell: bool = Field(
        default=False, description="是否在该位置插入新 cell（而非替换）"
    )


@tool(
    description="编辑或插入 Jupyter notebook 的 cell。可以修改现有 cell 的内容和类型，或在指定位置插入新 cell。",
    args_schema=NotebookEditInput,
)
def notebook_edit(
    file_path: str,
    cell_index: int,
    new_source: str,
    cell_type: str | None = None,
    new_cell: bool = False,
):
    try:
        import nbformat
    except ImportError:
        return "Error: nbformat is not installed. Run: pip install nbformat"

    resolved = Path(file_path).resolve()
    if not resolved.exists():
        return f"Error: File not found: {file_path}"

    try:
        nb = nbformat.read(str(resolved), as_version=4)

        if new_cell:
            ct = cell_type or "code"
            cell = (
                nbformat.v4.new_code_cell(source=new_source)
                if ct == "code"
                else nbformat.v4.new_markdown_cell(source=new_source)
            )
            nb.cells.insert(cell_index, cell)
            msg = f"Inserted new {ct} cell at index {cell_index}"
        else:
            if cell_index < 0 or cell_index >= len(nb.cells):
                return f"Error: cell_index {cell_index} out of range (0-{len(nb.cells) - 1})"
            nb.cells[cell_index]["source"] = new_source
            if cell_type:
                nb.cells[cell_index]["cell_type"] = cell_type
            msg = f"Updated cell {cell_index}"

        nbformat.write(nb, str(resolved))
        return f"{msg} in {file_path}"
    except Exception as e:
        return f"Error editing notebook: {e}"


# ==================== CreateFile ====================


class CreateFileInput(BaseModel):
    file_path: str = Field(description="要创建的文件的绝对路径")
    content: str = Field(description="文件内容")


@tool(
    description="创建一个新文件并写入内容。如果文件已存在则返回错误，防止意外覆盖。用于安全地创建新文件。",
    args_schema=CreateFileInput,
)
def create_file(file_path: str, content: str):
    resolved = Path(file_path).resolve()
    if resolved.exists():
        return f"Error: File already exists: {file_path}. Use edit_file or write_file to modify existing files."

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Successfully created {resolved} with {len(content)} characters"
    except Exception as e:
        return f"Error creating file: {e}"


# ==================== DeleteFile ====================


class DeleteFileInput(BaseModel):
    file_path: str = Field(description="要删除的文件的绝对路径")


@tool(
    description="删除指定的文件。此操作不可逆，请谨慎使用。删除前应确认文件路径正确。",
    args_schema=DeleteFileInput,
)
def delete_file(file_path: str):
    resolved = Path(file_path).resolve()
    if not resolved.exists():
        return f"Error: File not found: {file_path}"
    if not resolved.is_file():
        return f"Error: Not a file: {file_path}"

    try:
        resolved.unlink()
        return f"Successfully deleted {resolved}"
    except Exception as e:
        return f"Error deleting file: {e}"


# ==================== MoveFile ====================


class MoveFileInput(BaseModel):
    source: str = Field(description="源文件路径")
    destination: str = Field(description="目标文件路径")


@tool(
    description="移动或重命名文件。将源文件移动到目标路径，如果目标路径的父目录不存在会自动创建。",
    args_schema=MoveFileInput,
)
def move_file(source: str, destination: str):
    src = Path(source).resolve()
    dst = Path(destination).resolve()

    if not src.exists():
        return f"Error: Source not found: {source}"
    if not src.is_file():
        return f"Error: Source is not a file: {source}"
    if dst.exists():
        return f"Error: Destination already exists: {destination}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Successfully moved {src} -> {dst}"
    except Exception as e:
        return f"Error moving file: {e}"


# ==================== CopyFile ====================


class CopyFileInput(BaseModel):
    source: str = Field(description="源文件路径")
    destination: str = Field(description="目标文件路径")


@tool(
    description="复制文件到目标路径。如果目标路径的父目录不存在会自动创建。",
    args_schema=CopyFileInput,
)
def copy_file(source: str, destination: str):
    src = Path(source).resolve()
    dst = Path(destination).resolve()

    if not src.exists():
        return f"Error: Source not found: {source}"
    if not src.is_file():
        return f"Error: Source is not a file: {source}"
    if dst.exists():
        return f"Error: Destination already exists: {destination}"

    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        return f"Successfully copied {src} -> {dst}"
    except Exception as e:
        return f"Error copying file: {e}"


# ==================== KillShell ====================


class KillShellInput(BaseModel):
    pid: int = Field(description="要终止的进程 ID")


@tool(
    description="终止指定 PID 的后台 shell 进程。当某个命令长时间运行或挂起时使用此工具来终止它。",
    args_schema=KillShellInput,
)
def kill_shell(pid: int):
    import platform

    is_windows = platform.system() == "Windows"

    try:
        cmd = (
            ["taskkill", "/PID", str(pid), "/F"]
            if is_windows
            else ["kill", "-9", str(pid)]
        )
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            return f"Successfully terminated process {pid}"
        return f"Error terminating process {pid}: {proc.stderr.strip()}"
    except Exception as e:
        return f"Error: {e}"


# ==================== TaskAgent ====================


class TaskAgentInput(BaseModel):
    description: str = Field(
        description="要委派给子代理的任务描述，应清晰、具体、可执行"
    )
    subagent_type: str = Field(
        default="general",
        description="子代理类型：general（通用）、explore（代码探索）、code（代码编写）、test（测试生成）",
    )


@tool(
    description=(
        "启动一个子代理来执行复杂的多步骤任务。子代理拥有独立的上下文和工具访问权限，"
        "可以自主完成探索代码库、编写代码、生成测试等任务。"
        "适用于需要多轮搜索、分析和执行的复杂场景。"
    ),
    args_schema=TaskAgentInput,
)
def task_agent(description: str, subagent_type: str = "general"):
    return (
        f"[Task Agent] 已创建子代理任务：\n"
        f"  类型: {subagent_type}\n"
        f"  描述: {description}\n"
        f"  状态: pending\n\n"
        f"子代理将自主执行该任务并返回结果。"
    )


# ==================== GetTimeStr ====================


class GetTimeStrInput(BaseModel):
    type: str = Field("如果想获取日期，则传 day，如果想获取时间，则传 time")


@tool(description="获取当前时间字符串", args_schema=GetTimeStrInput)
def get_time_str(type: str):
    if type == "day":
        return datetime.now().strftime("%Y-%m-%d")
    return datetime.now().strftime("%Y-%m-%d %H-%M-%S")


# ==================== Tool Registry ====================


def get_agent_tool():
    return [
        read_file,
        write_file,
        edit_file,
        multi_edit,
        bash,
        glob_search,
        grep_search,
        list_directory,
        web_fetch,
        web_search,
        ask_user,
        todo_write,
        todo_read,
        notebook_read,
        notebook_edit,
        create_file,
        delete_file,
        move_file,
        copy_file,
        kill_shell,
        # task_agent,
        get_time_str,
    ]


