import os
import re
from pathlib import Path

from app.config import get_settings
from app.schemas.skill import SkillDetail, SkillMetadata, SkillParameter
from app.tools.sandbox import SandboxResult, execute_script
from app.utils.exceptions import SkillNotFound


_skills_registry: dict[str, dict] = {}


def load_skills_metadata() -> dict[str, SkillMetadata]:
    settings = get_settings()
    skills_dir = Path(settings.agent.SKILLS_DIR)

    if not skills_dir.exists():
        return {}

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            metadata = _parse_yaml_frontmatter(skill_md)
            if not metadata.get("name") or not metadata.get("description") or not metadata.get("version"):
                continue

            _skills_registry[metadata["name"]] = {
                "path": str(skill_dir),
                "metadata": metadata,
                "enabled": True,
            }
        except Exception:
            continue

    result = {}
    for name, info in _skills_registry.items():
        meta = info["metadata"]
        result[name] = SkillMetadata(
            name=meta["name"],
            description=meta["description"],
            version=meta["version"],
            enabled=info["enabled"],
            layer_1_loaded=True,
            layer_2_ready=False,
            author=meta.get("author"),
            license=meta.get("license"),
        )
    return result


def get_all_skills() -> list[SkillMetadata]:
    if not _skills_registry:
        load_skills_metadata()
    return [
        SkillMetadata(
            name=info["metadata"]["name"],
            description=info["metadata"]["description"],
            version=info["metadata"]["version"],
            enabled=info["enabled"],
            layer_1_loaded=True,
            layer_2_ready=False,
            author=info["metadata"].get("author"),
            license=info["metadata"].get("license"),
        )
        for info in _skills_registry.values()
    ]


def get_skill_detail(name: str) -> SkillDetail:
    if name not in _skills_registry:
        raise SkillNotFound(message=f"Skill '{name}' not found")

    info = _skills_registry[name]
    skill_md_path = Path(info["path"]) / "SKILL.md"
    content = skill_md_path.read_text(encoding="utf-8")

    body = _extract_markdown_body(content)
    params = _extract_parameters(content)

    meta = info["metadata"]
    return SkillDetail(
        name=meta["name"],
        description=meta["description"],
        version=meta["version"],
        enabled=info["enabled"],
        layer_1_loaded=True,
        layer_2_ready=True,
        author=meta.get("author"),
        license=meta.get("license"),
        instructions=body,
        parameters=params,
    )


def toggle_skill(name: str, enabled: bool) -> dict:
    if name not in _skills_registry:
        raise SkillNotFound(message=f"Skill '{name}' not found")

    if enabled:
        skill_md_path = Path(_skills_registry[name]["path"]) / "SKILL.md"
        if not _validate_skill_md(skill_md_path):
            return {"name": name, "enabled": False, "validated": False}

    _skills_registry[name]["enabled"] = enabled
    return {"name": name, "enabled": enabled, "validated": True}


async def execute_skill(name: str, args: dict) -> SandboxResult:
    if name not in _skills_registry:
        raise SkillNotFound(message=f"Skill '{name}' not found")

    skill_path = Path(_skills_registry[name]["path"]) / "scripts"
    script = _find_script(skill_path)
    if not script:
        return SandboxResult(exit_code=-1, stderr="No executable script found")

    return await execute_script(str(script), args, cwd=str(skill_path))


def _parse_yaml_frontmatter(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    yaml_str = match.group(1)
    result = {}
    for line in yaml_str.strip().split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _extract_markdown_body(content: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", content, re.DOTALL)
    return match.group(1).strip() if match else ""


def _extract_parameters(content: str) -> list[SkillParameter]:
    params = []
    param_match = re.search(r"# Parameters?\s*\n(.*?)(?=\n#|\Z)", content, re.DOTALL)
    if param_match:
        for line in param_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("-"):
                param_str = line.lstrip("- ").strip()
                name = param_str.split(":")[0].strip() if ":" in param_str else param_str
                params.append(SkillParameter(name=name, type="string", required=True, description=None))
    return params


def _validate_skill_md(path: Path) -> bool:
    try:
        meta = _parse_yaml_frontmatter(path)
        return bool(meta.get("name") and meta.get("description") and meta.get("version"))
    except Exception:
        return False


def _find_script(scripts_dir: Path) -> Path | None:
    if not scripts_dir.exists():
        return None
    for f in scripts_dir.iterdir():
        if f.suffix == ".py":
            return f
    return None
