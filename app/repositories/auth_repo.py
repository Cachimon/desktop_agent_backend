from datetime import datetime, timedelta

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_auth import UserAuth, VerificationCode, RefreshToken, RateLimit
from app.repositories.base import BaseRepository


class AuthRepo(BaseRepository[UserAuth]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserAuth, session)
        self.session = session

    async def get_by_email(self, email: str) -> UserAuth | None:
        stmt = select(UserAuth).where(UserAuth.email == email)
        return await self.get_one(stmt)

    async def create_user(self, email: str) -> UserAuth:
        user = UserAuth(email=email)
        return await self.create(user)

    async def create_verification_code(
        self, email: str, code_hash: str, expires_at: datetime
    ) -> VerificationCode:
        vc = VerificationCode(email=email, code_hash=code_hash, expires_at=expires_at)
        self.session.add(vc)
        await self.session.flush()
        return vc

    async def get_latest_valid_code(self, email: str) -> VerificationCode | None:
        now = datetime.utcnow()
        stmt = (
            select(VerificationCode)
            .where(
                and_(
                    VerificationCode.email == email,
                    VerificationCode.used_at.is_(None),
                    VerificationCode.expires_at > now,
                )
            )
            .order_by(VerificationCode.created_at.desc())
            .limit(1)
        )
        return await self.get_one(stmt)

    async def mark_code_used(self, code_id: int) -> None:
        vc = await self.session.get(VerificationCode, code_id)
        if vc:
            vc.used_at = datetime.utcnow()
            await self.session.flush()

    async def increment_code_attempts(self, code_id: int) -> int:
        vc = await self.session.get(VerificationCode, code_id)
        if vc:
            vc.attempt_count += 1
            await self.session.flush()
            return vc.attempt_count
        return 0

    async def invalidate_code(self, code_id: int) -> None:
        vc = await self.session.get(VerificationCode, code_id)
        if vc:
            vc.used_at = datetime.utcnow()
            await self.session.flush()

    async def create_refresh_token(
        self, user_id: int, token_hash: str, expires_at: datetime
    ) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return await self.get_one(stmt)

    async def revoke_refresh_token(self, token_id: int) -> None:
        rt = await self.session.get(RefreshToken, token_id)
        if rt:
            rt.revoked_at = datetime.utcnow()
            await self.session.flush()

    async def revoke_all_user_tokens(self, user_id: int) -> None:
        stmt = select(RefreshToken).where(
            and_(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        )
        tokens = await self.get_many(stmt)
        now = datetime.utcnow()
        for t in tokens:
            t.revoked_at = now
        await self.session.flush()

    async def get_rate_limit(
        self, identifier: str, action_type: str
    ) -> RateLimit | None:
        stmt = select(RateLimit).where(
            and_(RateLimit.identifier == identifier, RateLimit.action_type == action_type)
        )
        return await self.get_one(stmt)

    async def upsert_rate_limit(
        self, identifier: str, action_type: str, window_start: datetime
    ) -> RateLimit:
        rl = await self.get_rate_limit(identifier, action_type)
        if rl and rl.window_start >= window_start:
            rl.attempt_count += 1
        else:
            rl = RateLimit(
                identifier=identifier,
                action_type=action_type,
                attempt_count=1,
                window_start=window_start,
            )
            self.session.add(rl)
        await self.session.flush()
        return rl

    async def reset_rate_limit(self, identifier: str, action_type: str) -> None:
        rl = await self.get_rate_limit(identifier, action_type)
        if rl:
            await self.session.delete(rl)
            await self.session.flush()

    async def count_codes_sent_today(self, email: str) -> int:
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        stmt = select(func.count()).select_from(VerificationCode).where(
            and_(VerificationCode.email == email, VerificationCode.created_at >= today_start)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count_recent_login_failures(self, email: str, window_minutes: int = 15) -> int:
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=window_minutes)
        rl = await self.get_rate_limit(email, "login_failure")
        if rl and rl.window_start >= window_start:
            return rl.attempt_count
        return 0

    async def count_emails_for_ip(self, ip_address: str, window_hours: int = 1) -> int:
        now = datetime.utcnow()
        window_start = now - timedelta(hours=window_hours)
        stmt = select(func.count(VerificationCode.email.distinct())).select_from(VerificationCode).where(
            and_(
                VerificationCode.created_at >= window_start,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
