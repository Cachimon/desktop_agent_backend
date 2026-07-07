from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user
from app.models.base import get_db_session
from app.schemas.skill import SkillDetail, SkillListResponse, SkillMetadata, SkillToggleRequest, SkillToggleResponse
# from app.services.skill_service import get_all_skills, get_skill_detail, toggle_skill

router = APIRouter(prefix="/skills", tags=["Skills"])


@router.get("", response_model=SkillListResponse)
async def list_skills(
    user: dict = Depends(get_current_user),
):
    skills = get_all_skills()
    return SkillListResponse(skills=skills)


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(
    name: str,
    user: dict = Depends(get_current_user),
):
    return get_skill_detail(name)


@router.post("/{name}/toggle", response_model=SkillToggleResponse)
async def toggle_skill_endpoint(
    name: str,
    body: SkillToggleRequest,
    user: dict = Depends(get_current_user),
):
    result = toggle_skill(name, body.enabled)
    return SkillToggleResponse(**result)
