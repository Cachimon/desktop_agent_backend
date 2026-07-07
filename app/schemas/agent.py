from dataclasses import dataclass, field


@dataclass
class SkillMeta:
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    enabled: bool = True
    file_path: str = ""
    skill_type: str = "knowledge"  # knowledge | script


@dataclass
class SkillEntry:
    meta: SkillMeta
    raw_content: str = ""
    instructions: str = ""
    parameters: list[dict] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    skill_dir: str = ""


@dataclass
class SkillRegistry:
    skills: dict[str, SkillEntry] = field(default_factory=dict)
    skills_dir: str = ""
