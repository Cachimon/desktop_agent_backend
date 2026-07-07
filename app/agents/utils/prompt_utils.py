from functools import lru_cache
from pathlib import Path
import platform

from app.schemas.agent import SkillRegistry
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _get_prompt_path():
    return Path(__file__).resolve().parent.parent / "prompts"


def _has_git_intent(messages: list) -> bool:
    """检查最近的用户消息是否涉及 git 操作"""
    for msg in reversed(messages[-3:]):  # 只看最近 3 条
        text = ""
        if isinstance(msg.content, str):
            text = msg.content.lower()
        elif isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text += part.get("text", "").lower()
        _GIT_KEYWORDS = {
            "commit",
            "push",
            "pull",
            "merge",
            "rebase",
            "branch",
            "checkout",
            "stash",
            "diff",
            "log",
            "blame",
            "reset",
            "git",
            "提交",
            "推送",
            "拉取",
            "合并",
            "分支",
            "pull request",
            "pr",
            "代码审查",
        }
        if any(kw in text for kw in _GIT_KEYWORDS):
            return True
    return False


def _extract_text(msg) -> str:
    if isinstance(msg.content, str):
        return msg.content
    if isinstance(msg.content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in msg.content
        )
    return ""


def _has_review_intent(messages: list) -> bool:
    _REVIEW_KEYWORDS = {
        "review",
        "审查",
        "检查代码",
        "代码审查",
        "看看这段代码",
        "有没有问题",
        "有没有 bug",
        "代码质量",
        "帮我看看",
        "code review",
        "review 一下",
    }
    for msg in reversed(messages[-3:]):
        text = _extract_text(msg).lower()
        if any(kw in text for kw in _REVIEW_KEYWORDS):
            return True
    return False


def read_md(resolve_path: Path) -> str:
    if not resolve_path or not resolve_path.exists():
        logger.error(f"没有找到md文件【{resolve_path}】")
        return ""
    content = resolve_path.read_text(encoding="utf-8", errors="replace")
    return content


@lru_cache
def get_sys_prompt():
    print("get sys prompt")
    should_load_list = [
        "system.md",
        "tool_guidelines.md",
        "human_interaction.md",
    ]
    _sys_prompt = ""
    for md_file in should_load_list:
        _path = _get_prompt_path() / md_file
        _sys_prompt += read_md(_path)
    _sys_prompt += _build_platform_hint()
    return _sys_prompt


def _build_platform_hint() -> str:
    system = platform.system()
    if system == "Windows":
        return (
            "\n## 运行环境\n"
            "- 当前运行在 **Windows** 系统上\n"
            "- 使用 `cd`（不带参数）获取当前目录，而非 `pwd`\n"
            "- 使用 `dir` 列出目录内容，而非 `ls`\n"
            "- 使用 `type` 查看文件内容，而非 `cat`\n"
            "- 使用 `del` 删除文件，而非 `rm`\n"
            "- 使用 `copy` 复制文件，而非 `cp`\n"
            "- 使用 `move` 移动文件，而非 `mv`\n"
            "- 路径使用反斜杠 `\\` 或正斜杠 `/` 均可\n"
        )
    return ""


def get_git_prompt(messages: list) -> str:
    if _has_git_intent(messages):
        should_load_list = [
            "git_safety.md",
            "commit_message.md",
            "pr_description.md",
        ]
        _prompt = ""
        for md_file in should_load_list:
            _path = _get_prompt_path() / md_file
            _prompt += read_md(_path)
        return _prompt
    return ""


def get_review_prompt(messages: list) -> str:
    if _has_review_intent(messages):
        should_load_list = ["review.md"]
        _prompt = ""
        for md_file in should_load_list:
            _path = _get_prompt_path() / md_file
            _prompt += read_md(_path)
        return _prompt
    return ""


def load_skill_instructions(registry: SkillRegistry, skill_name: str) -> str:
    """
    Layer 2: 加载指定 skill 的完整 instructions，用于注入 system prompt。

    Claude Code 的两层加载：
    - Layer 1: 启动时只加载 description（轻量，始终在 prompt 中）
    - Layer 2: 匹配后才加载完整 instructions（重量，按需注入）

    这样做的好处：
    1. 减少 token 消耗 - 不是所有 skill 的完整内容都始终在上下文中
    2. 提高匹配精度 - LLM 先看简短描述判断是否需要，再看详细指令执行
    """
    if skill_name not in registry.skills:
        return f"[Skill '{skill_name}' not found]"

    entry = registry.skills[skill_name]
    if not entry.meta.enabled:
        return f"[Skill '{skill_name}' is disabled]"

    parts = [f"## Skill: {entry.meta.name}", ""]

    if entry.skill_dir:
        parts.append("### Skill folder location")
        parts.append(entry.skill_dir)

    if entry.parameters:
        parts.append("### Parameters")
        for p in entry.parameters:
            req = "required" if p.get("required") else "optional"
            parts.append(f"- `{p['name']}` ({p.get('type', 'string')}, {req})")
        parts.append("")

    if entry.scripts:
        parts.append("### Available Scripts")
        for s in entry.scripts:
            parts.append(f"- `{s}`")
        parts.append("")

    parts.append("### Instructions")
    parts.append(entry.instructions)

    return "\n".join(parts)


def build_layer1_prompt(registry: SkillRegistry) -> str:
    """
    Layer 1: 把所有 skill 的 description 放进 system prompt。
    这就是 Claude Code 让 LLM "自行判断" 的方式。
    """
    print("build_layer1_prompt")
    if not registry.skills:
        return ""

    lines = [
        "## Available Skills",
        "你先自行匹配出一个skill，然后再调用加载指令的工具获取指令。",
        "",
    ]
    for name, entry in registry.skills.items():
        if not entry.meta.enabled:
            continue
        desc = entry.meta.description
        lines.append(f"- **{name}**: {desc}")

    lines.append("")
    lines.extend(
        [
            "**重要规则：**"
            "- 当用户的需求匹配以上某个 skill 的描述时，你应该在回复中说明你正在使用该 skill",
            "- 同一个需求可能匹配多个 skill，选择最相关的一个"
            "- 确认使用哪个skill之后，再获取 skill 的完整指令，根据该指令操作。",
        ]
    )
    return "\n".join(lines)


def build_layer2_prompt(skill_name: str, instructions: str) -> str:
    """
    Layer 2: 匹配后，把该 skill 的完整 instructions 追加到 prompt。
    """
    print("build_layer2_prompt")
    parts = ["## Active Skill: {skill_name}"]
    parts.append(f"\n你已激活 skill `{skill_name}`，请严格按照以下指令执行：\n")
    parts.append(instructions)
    parts.append("请根据以上指令，使用你的工具完成用户的请求。\n")
    parts.append("\n")

    return "\n".join(parts)


def build_skill_aware_prompt(
    base_prompt: str,
    registry: SkillRegistry,
    activated_skills: list[str] | None = None,
) -> str:
    """
    在 LangGraph agent_node 中构建 prompt 的推荐方式。
    """
    parts = [base_prompt]

    # Layer 1: 始终包含
    parts.append(build_layer1_prompt(registry))

    # Layer 2: 按需包含
    if activated_skills:
        parts.append("## Active Skill: {skill_name}")
        for skill_name in activated_skills:
            if (
                skill_name in registry.skills
                and registry.skills[skill_name].meta.enabled
            ):
                parts.append(
                    f"\n你已激活 skill `{skill_name}`，请严格按照以下指令执行：\n"
                )
                instructions = load_skill_instructions(registry, skill_name)
                parts.append(instructions)
                parts.append("请根据以上指令，使用你的工具完成用户的请求。\n")

    return "\n\n".join(parts)


if __name__ == "__main__":
    # cwd = Path(__file__).resolve().parent.parent / "prompts"
    # print(cwd.exists())

    test_arr = []
    test_arr.append(
        [
            "ssss",
            "ddddd",
            "ssss",
        ]
    )
    print(test_arr)
