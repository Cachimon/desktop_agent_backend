import secrets
from datetime import datetime, timedelta

import aiosmtplib
from email.mime.text import MIMEText
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.repositories.auth_repo import AuthRepo
from app.security.rate_limiter import (
    check_account_lockout,
    check_ip_anomaly,
    check_ip_rate_limit,
    check_send_code_rate_limit,
    increment_login_failure,
    increment_send_code,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)
from app.security.token import (
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_access_token,
    verify_token_hash,
)
from app.security.audit_logger import record_audit
from app.utils.exceptions import (
    CodeAlreadyUsed,
    CodeMaxAttemptsExceeded,
    InvalidCode,
    InvalidRefreshToken,
    NotAuthenticated,
    TokenReuseDetected,
)


async def send_verification_code(email: str, client_ip: str, session: AsyncSession) -> dict:
    settings = get_settings()
    repo = AuthRepo(session)

    await check_ip_rate_limit(client_ip, session)
    await check_ip_anomaly(client_ip, session)

    try:
        await check_send_code_rate_limit(email, session)
    except Exception:
        return {"message": "If the email is registered, a verification code has been sent"}

    code = "".join(secrets.choice("0123456789") for _ in range(settings.auth.VERIFICATION_CODE_LENGTH))
    code_hash = hash_token(code)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.auth.VERIFICATION_CODE_EXPIRE_MINUTES)

    await repo.create_verification_code(email, code_hash, expires_at)
    await increment_send_code(email, session)

    try:
        await _send_email(email, code, settings)
    except Exception as e:
        logger.error("email_send_failed", email=email, error=str(e))
        return {"message": "If the email is registered, a verification code has been sent"}

    await record_audit(
        session, operation="auth_send_code",
        details={"email": email},
        ip_address=client_ip, risk_level="low", status="completed",
    )

    logger.info("verification_code_sent", email=email)

    return {"message": "If the email is registered, a verification code has been sent"}


async def login(email: str, code: str, client_ip: str, session: AsyncSession) -> dict:
    settings = get_settings()
    repo = AuthRepo(session)

    await check_account_lockout(email, session)

    vc = await repo.get_latest_valid_code(email)
    if not vc:
        raise InvalidCode(message="Invalid or expired verification code")

    if vc.used_at is not None:
        raise CodeAlreadyUsed(message="Verification code has already been used")

    if not verify_token_hash(code, vc.code_hash):
        attempts = await repo.increment_code_attempts(vc.id)
        if attempts >= settings.auth.VERIFICATION_CODE_MAX_ATTEMPTS:
            await repo.invalidate_code(vc.id)
            raise CodeMaxAttemptsExceeded(message="Maximum attempts exceeded for this code")
        await increment_login_failure(email, session)
        raise InvalidCode(message="Invalid verification code")

    await repo.mark_code_used(vc.id)

    user = await repo.get_by_email(email)
    if not user:
        user = await repo.create_user(email)

    if not user.is_active:
        raise NotAuthenticated(message="Account is deactivated")

    access_token = create_access_token(user.id, user.email)
    refresh_token_str = create_refresh_token()
    refresh_token_hash = hash_token(refresh_token_str)
    expires_at = datetime.utcnow() + timedelta(days=settings.auth.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await repo.create_refresh_token(user.id, refresh_token_hash, expires_at)

    await record_audit(
        session, operation="auth_login",
        details={"email": email},
        ip_address=client_ip, user_id=str(user.id),
        risk_level="low", status="completed",
    )

    logger.info("user_login", user_id=user.id, email=email)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.auth.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
        "refresh_token": refresh_token_str,
    }


async def refresh_token(old_token: str, session: AsyncSession) -> dict:
    settings = get_settings()
    repo = AuthRepo(session)

    token_hash = hash_token(old_token)
    rt = await repo.get_refresh_token_by_hash(token_hash)

    if not rt or rt.revoked_at is not None or rt.expires_at < datetime.utcnow():
        raise InvalidRefreshToken(message="Invalid or expired refresh token")

    user = await repo.get_by_id(rt.user_id)
    if not user or not user.is_active:
        raise InvalidRefreshToken(message="User account not found or deactivated")

    await repo.revoke_refresh_token(rt.id)

    access_token = create_access_token(user.id, user.email)
    new_refresh_token = create_refresh_token()
    new_hash = hash_token(new_refresh_token)
    expires_at = datetime.utcnow() + timedelta(days=settings.auth.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await repo.create_refresh_token(user.id, new_hash, expires_at)

    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.auth.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": {
            "id": user.id,
            "email": user.email,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
        },
        "refresh_token": new_refresh_token,
    }


async def detect_token_reuse(old_token: str, session: AsyncSession) -> None:
    repo = AuthRepo(session)
    token_hash = hash_token(old_token)
    rt = await repo.get_refresh_token_by_hash(token_hash)

    if rt and rt.revoked_at is not None:
        await repo.revoke_all_user_tokens(rt.user_id)
        raise TokenReuseDetected(message="Token reuse detected. All sessions have been invalidated.")


async def logout(user_id: int, refresh_token_str: str | None, session: AsyncSession) -> dict:
    repo = AuthRepo(session)

    if refresh_token_str:
        token_hash = hash_token(refresh_token_str)
        rt = await repo.get_refresh_token_by_hash(token_hash)
        if rt:
            await repo.revoke_refresh_token(rt.id)

    await record_audit(
        session, operation="auth_logout",
        user_id=str(user_id), risk_level="low", status="completed",
    )

    return {"message": "Logged out successfully"}


async def get_current_user_info(user_id: int, session: AsyncSession) -> dict:
    repo = AuthRepo(session)
    user = await repo.get_by_id(user_id)
    if not user:
        raise NotAuthenticated(message="User not found")
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat(),
    }


async def _send_email(to_email: str, code: str, settings) -> None:
    subject = "AI Desktop Agent - Verification Code"
    body = (
        f"Your verification code is: {code}\n\n"
        f"This code expires in {settings.auth.VERIFICATION_CODE_EXPIRE_MINUTES} minutes.\n\n"
        f"Security Warning: Do not share this code with anyone. "
        f"If you did not request this code, please ignore this email."
    )

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = settings.auth.SMTP_USER
    msg["To"] = to_email

    await aiosmtplib.send(
        msg,
        hostname=settings.auth.SMTP_HOST,
        port=settings.auth.SMTP_PORT,
        username=settings.auth.SMTP_USER,
        password=settings.auth.SMTP_PASSWORD,
        use_tls=settings.auth.SMTP_USE_TLS,
    )
