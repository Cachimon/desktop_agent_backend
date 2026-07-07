import os
import re
from pathlib import Path

from app.config import get_settings
from app.schemas.agent import SkillRegistry, SkillEntry, SkillMeta
from app.schemas.skill import SkillDetail, SkillMetadata, SkillParameter
from app.tools.sandbox import SandboxResult, execute_script
from app.utils.exceptions import SkillNotFound
from app.utils.logging import get_logger

_skills_registry: SkillRegistry | None = None

logger = get_logger(__name__)


def _parse_skill_file(file_path: Path, is_single_file: bool) -> SkillEntry | None:
    content = file_path.read_text(encoding="utf-8", errors="replace")
    meta_dict = parse_yaml_frontmatter(content)

    if not meta_dict.get("name") or not meta_dict.get("description"):
        return None

    instructions = extract_markdown_body(content)
    parameters = extract_parameters(content)

    if is_single_file:
        skill_dir = str(file_path.parent)
        scripts = []
        skill_type = "knowledge"
    else:
        skill_dir = str(file_path.parent)
        scripts_dir = file_path.parent / "scripts"
        scripts = (
            [f.name for f in scripts_dir.glob("*.py")] if scripts_dir.exists() else []
        )
        skill_type = "script" if scripts else "knowledge"

    return SkillEntry(
        meta=SkillMeta(
            name=meta_dict["name"],
            description=meta_dict["description"],
            version=meta_dict.get("version", "1.0.0"),
            author=meta_dict.get("author", ""),
            enabled=True,
            file_path=str(file_path),
            skill_type=skill_type,
        ),
        raw_content=content,
        instructions=instructions,
        parameters=parameters,
        scripts=scripts,
        skill_dir=skill_dir,
    )


def discover_skills(skills_dir: str) -> SkillRegistry:
    """
    扫描 skill 目录，发现所有 skill 文件。

    支持两种格式：
    - 单文件：skills_dir/batch-rename.md
    - 目录：skills_dir/batch-rename/SKILL.md

    对应 Claude Code 启动时的 skill discovery 阶段。
    """
    registry = SkillRegistry(skills_dir=skills_dir)
    root = Path(skills_dir).resolve()

    if not root.exists():
        logger.error(f"Skills dir not found: {skills_dir}")
        return registry

    # 扫描单文件格式 .md
    for md_file in sorted(root.glob("*.md")):
        try:
            entry = _parse_skill_file(md_file, is_single_file=True)
            if entry:
                registry.skills[entry.meta.name] = entry
        except Exception as e:
            logger.error(f"Failed to parse skill file: {md_file}", error=str(e))
            continue

    # 扫描目录格式 SKILL.md
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            logger.error(f"Invalid skill dir: {skill_dir}")
            continue
        skill_md = skill_dir / "SKILL.md"
        print("md", skill_md, skill_md.exists())
        if not skill_md.exists():
            logger.error(f"SKILL.md not found in dir: {skill_md}")
            continue
        try:
            entry = _parse_skill_file(skill_md, is_single_file=False)
            if entry:
                registry.skills[entry.meta.name] = entry
        except Exception as e:
            logger.error(f"Failed to parse skill dir: {skill_dir}", error=str(e))
            continue
    global _skills_registry
    _skills_registry = registry
    return registry


def get_skill_registry() -> SkillRegistry:
    if not _skills_registry:
        settings = get_settings()
        skills_dir = settings.agent_cfg.SKILLS_DIR
        discover_skills(skills_dir)
    return _skills_registry


def parse_yaml_frontmatter(content: str) -> dict:
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}
    result = {}
    for line in match.group(1).strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def extract_markdown_body(content: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", content, re.DOTALL)
    return match.group(1).strip() if match else ""


def extract_parameters(content: str) -> list[dict]:
    params = []
    param_match = re.search(r"# Parameters?\s*\n(.*?)(?=\n#|\Z)", content, re.DOTALL)
    if param_match:
        for line in param_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("-"):
                param_str = line.lstrip("- ").strip()
                name = (
                    param_str.split(":")[0].strip() if ":" in param_str else param_str
                )
                params.append({"name": name, "type": "string", "required": True})
    return params





def match_skills_by_keywords(user_input: str, top_k: int = 3) -> list[str]:
    """
    基于关键词的 skill 匹配（Claude Code 的轻量匹配方式）。

    将用户输入与每个 skill 的 description 做关键词重叠匹配。
    Claude Code 实际上不单独做这一步——它把 description 放在 prompt 里让 LLM 自行判断。
    但这个方法可以作为辅助，用于在 LLM 调用前的预筛选。
    """
    registry = get_skill_registry()
    user_tokens = set(re.findall(r"\w+", user_input.lower()))

    scored = []
    for name, entry in registry.skills.items():
        if not entry.meta.enabled:
            continue
        desc_tokens = set(re.findall(r"\w+", entry.meta.description.lower()))
        overlap = len(user_tokens & desc_tokens)
        if overlap > 0:
            scored.append((name, overlap))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [name for name, _ in scored[:top_k]]



def enable_skill(name: str, enabled: bool = True) -> bool:
    registry = get_skill_registry()
    if name not in registry.skills:
        return False
    registry.skills[name].meta.enabled = enabled
    return True


def validate_skill(skill_path: str) -> tuple[bool, list[str]]:
    """
    验证 skill 结构是否合法。
    返回 (是否合法, 错误/警告列表)
    """
    path = Path(skill_path).resolve()
    issues = []

    # 单文件格式
    if path.is_file() and path.suffix == ".md":
        content = path.read_text(encoding="utf-8", errors="replace")
        meta = parse_yaml_frontmatter(content)
        if not meta.get("name"):
            issues.append("缺少 name 字段")
        if not meta.get("description"):
            issues.append("缺少 description 字段")
        body = extract_markdown_body(content)
        if not body:
            issues.append("警告: 没有 Instructions 内容")
        return len([i for i in issues if not i.startswith("警告")]) == 0, issues

    # 目录格式
    if path.is_dir():
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            return False, ["SKILL.md 不存在"]
        content = skill_md.read_text(encoding="utf-8", errors="replace")
        meta = parse_yaml_frontmatter(content)
        if not meta.get("name"):
            issues.append("缺少 name 字段")
        if not meta.get("description"):
            issues.append("缺少 description 字段")
        body = extract_markdown_body(content)
        if not body:
            issues.append("警告: 没有 Instructions 内容")
        scripts_dir = path / "scripts"
        if not scripts_dir.exists():
            issues.append("警告: scripts 目录不存在（纯知识型 skill 可忽略）")
        return len([i for i in issues if not i.startswith("警告")]) == 0, issues

    return False, [f"无效路径: {skill_path}"]


def create_skill(
    skills_dir: str,
    name: str,
    description: str,
    instructions: str,
    version: str = "1.0.0",
    author: str = "",
    script_content: str | None = None,
) -> tuple[bool, str]:
    """
    创建新 skill，返回 (是否成功, 路径或错误信息)。
    默认使用单文件格式（Claude Code 原生风格），有脚本时使用目录格式。
    """
    root = Path(skills_dir).resolve()

    if script_content:
        # 目录格式
        skill_dir = root / name
        if skill_dir.exists():
            return False, f"Skill '{name}' 目录已存在"
        skill_dir.mkdir(parents=True, exist_ok=True)

        md_content = f'---\nname: {name}\ndescription: {description}\nversion: "{version}"\nauthor: {author}\n---\n\n# Instructions\n{instructions}\n'
        (skill_dir / "SKILL.md").write_text(md_content, encoding="utf-8")

        scripts_dir = skill_dir / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        (scripts_dir / f"{name.replace('-', '_')}.py").write_text(
            script_content, encoding="utf-8"
        )

        return True, str(skill_dir)
    else:
        # 单文件格式（Claude Code 原生）
        md_path = root / f"{name}.md"
        if md_path.exists():
            return False, f"Skill '{name}' 文件已存在"
        root.mkdir(parents=True, exist_ok=True)

        md_content = f'---\nname: {name}\ndescription: {description}\nversion: "{version}"\nauthor: {author}\n---\n\n# Instructions\n{instructions}\n'
        md_path.write_text(md_content, encoding="utf-8")

        return True, str(md_path)

def reload_registry() -> int:
    """热重载 skill 注册表，返回 skill 数量。"""
    registry = get_skill_registry()
    new_registry = discover_skills(registry.skills_dir)
    registry.skills = new_registry.skills
    return len(registry.skills)


def list_skills(enabled_only: bool = True) -> list[dict]:
    """列出所有 skill 的元数据。"""
    registry = get_skill_registry()
    result = []
    for name, entry in registry.skills.items():
        if enabled_only and not entry.meta.enabled:
            continue
        result.append(
            {
                "name": entry.meta.name,
                "description": entry.meta.description,
                "version": entry.meta.version,
                "enabled": entry.meta.enabled,
                "type": entry.meta.skill_type,
                "scripts": entry.scripts,
            }
        )
    return result

