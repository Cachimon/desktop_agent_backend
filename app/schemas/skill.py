from pydantic import BaseModel


class SkillParameter(BaseModel):
    name: str
    type: str
    required: bool
    description: str | None = None


class SkillMetadata(BaseModel):
    name: str
    description: str
    version: str
    enabled: bool
    layer_1_loaded: bool
    layer_2_ready: bool = False
    author: str | None = None
    license: str | None = None


class SkillDetail(SkillMetadata):
    instructions: str
    parameters: list[SkillParameter] = []


class SkillToggleRequest(BaseModel):
    enabled: bool


class SkillToggleResponse(BaseModel):
    name: str
    enabled: bool
    validated: bool


class SkillListResponse(BaseModel):
    skills: list[SkillMetadata]
