from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.user_auth import RateLimit
from app.repositories.auth_repo import AuthRepo
from app.utils.exceptions import (
    RateLimitExceeded,
    IPRateLimitExceeded,
    AccountLocked,
    AnomalousIPDetected,
)


async def check_send_code_rate_limit(email: str, session: AsyncSession) -> None:
    settings = get_settings()
    repo = AuthRepo(session)

    rl = await repo.get_rate_limit(email, "send_code")
    now = datetime.utcnow()

    if rl and rl.window_start:
        elapsed = (now - rl.window_start).total_seconds()
        if elapsed < settings.auth.SEND_CODE_COOLDOWN_SECONDS and rl.attempt_count > 0:
            remaining = int(settings.auth.SEND_CODE_COOLDOWN_SECONDS - elapsed)
            raise RateLimitExceeded(
                message=f"Please wait {remaining}s before requesting a new code",
                detail={"remaining_seconds": remaining},
            )

    daily_count = await repo.count_codes_sent_today(email)
    if daily_count >= settings.auth.SEND_CODE_DAILY_LIMIT:
        raise RateLimitExceeded(
            message="Daily verification code limit exceeded",
            detail={"daily_limit": settings.auth.SEND_CODE_DAILY_LIMIT},
        )


async def check_ip_rate_limit(ip_address: str, session: AsyncSession) -> None:
    settings = get_settings()
    repo = AuthRepo(session)

    rl = await repo.get_rate_limit(ip_address, "global_request")
    now = datetime.utcnow()

    if rl and rl.window_start:
        elapsed = (now - rl.window_start).total_seconds()
        if elapsed < 60:
            if rl.attempt_count >= settings.auth.IP_RATE_LIMIT_PER_MINUTE:
                raise IPRateLimitExceeded(
                    message="IP rate limit exceeded",
                    detail={"limit": settings.auth.IP_RATE_LIMIT_PER_MINUTE, "window": "60s"},
                )
        else:
            await repo.upsert_rate_limit(ip_address, "global_request", now)
    else:
        await repo.upsert_rate_limit(ip_address, "global_request", now)


async def check_account_lockout(email: str, session: AsyncSession) -> None:
    settings = get_settings()
    repo = AuthRepo(session)

    rl = await repo.get_rate_limit(email, "login_failure")
    now = datetime.utcnow()

    if rl and rl.window_start:
        elapsed = (now - rl.window_start).total_seconds()
        lockout_seconds = settings.auth.LOGIN_FAILURE_LOCKOUT_DURATION_MINUTES * 60
        if rl.attempt_count >= settings.auth.LOGIN_FAILURE_LOCKOUT_THRESHOLD:
            if elapsed < lockout_seconds:
                remaining = int(lockout_seconds - elapsed)
                raise AccountLocked(
                    message=f"Account locked for {remaining}s",
                    detail={"remaining_seconds": remaining},
                )
            else:
                await repo.reset_rate_limit(email, "login_failure")


async def check_ip_anomaly(ip_address: str, session: AsyncSession) -> None:
    settings = get_settings()
    repo = AuthRepo(session)

    count = await repo.count_emails_for_ip(
        ip_address, window_hours=settings.auth.IP_ANOMALY_WINDOW_HOURS
    )
    if count >= settings.auth.IP_ANOMALY_EMAIL_THRESHOLD:
        raise AnomalousIPDetected(
            message="Anomalous activity detected from this IP",
            detail={"ip": ip_address},
        )


async def increment_login_failure(email: str, session: AsyncSession) -> None:
    repo = AuthRepo(session)
    now = datetime.utcnow()
    window_minutes = 15
    rl = await repo.get_rate_limit(email, "login_failure")

    if rl and rl.window_start:
        elapsed = (now - rl.window_start).total_seconds()
        if elapsed < window_minutes * 60:
            rl.attempt_count += 1
            await session.flush()
        else:
            rl.attempt_count = 1
            rl.window_start = now
            await session.flush()
    else:
        await repo.upsert_rate_limit(email, "login_failure", now)


async def increment_send_code(email: str, session: AsyncSession) -> None:
    repo = AuthRepo(session)
    now = datetime.utcnow()
    await repo.upsert_rate_limit(email, "send_code", now)
