from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import UserSetting
from app.repositories.base import BaseRepository


class SettingsRepo(BaseRepository[UserSetting]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserSetting, session)

    async def get_user_setting(self, user_id: str, setting_key: str) -> UserSetting | None:
        stmt = select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.setting_key == setting_key,
        )
        return await self.get_one(stmt)

    async def set_user_setting(
        self, user_id: str, setting_key: str, setting_value: dict
    ) -> UserSetting:
        existing = await self.get_user_setting(user_id, setting_key)
        if existing:
            existing.setting_value = setting_value
            await self.session.flush()
            return existing
        us = UserSetting(user_id=user_id, setting_key=setting_key, setting_value=setting_value)
        return await self.create(us)

    async def delete_user_setting(self, user_id: str, setting_key: str) -> bool:
        existing = await self.get_user_setting(user_id, setting_key)
        if existing:
            await self.delete(existing)
            return True
        return False
