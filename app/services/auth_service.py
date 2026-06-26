import secrets
from datetime import datetime, timedelta

import aiosmtplib
from email.mime.text import MIMEText

from fastapi import HTTPException
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
    TokenReuseDetected, RateLimitExceeded, AppException,
)


async def send_verification_code(email: str, client_ip: str, session: AsyncSession) -> dict:
    settings = get_settings()
    repo = AuthRepo(session)

    # 1. 安全检查：IP 限流
    await check_ip_rate_limit(client_ip, session)
    await check_ip_anomaly(client_ip, session)

    # 2. 业务检查：邮箱发送频率限制
    # FIX：异常处理逻辑合理化
    try:
        await check_send_code_rate_limit(email, session)
    except RateLimitExceeded as e:
        raise e
    except Exception as e:
        # 其他未知异常应该抛出，而不是吞掉
        logger.error("Rate limit check failed", error=str(e))
        raise AppException(message="System Error")

    # 3. 生成验证码
    code = "".join(secrets.choice("0123456789") for _ in range(settings.auth.VERIFICATION_CODE_LENGTH))
    code_hash = hash_token(code)
    expires_at = datetime.utcnow() + timedelta(minutes=settings.auth.VERIFICATION_CODE_EXPIRE_MINUTES)

    # 4. 存储验证码并发送邮件
    await repo.create_verification_code(email, code_hash, expires_at, client_ip)
    # TODO：应该在发送邮件成功后再加的，但是又考虑到并发场景要限制发送。
    await increment_send_code(email, session)

    # 5. 发送邮件（异步）
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
    """
    用户登录函数，验证用户提供的信息并返回访问和刷新令牌。

    参数:
    email (str): 用户的电子邮件地址。
    code (str): 用户提供的验证码。
    client_ip (str): 客户端的IP地址。
    session (AsyncSession): 数据库会话对象。

    返回:
    dict: 包含访问令牌、令牌类型、过期时间和用户信息的字典。

    异常:
    InvalidCode: 验证码无效或已过期。
    CodeAlreadyUsed: 验证码已被使用。
    CodeMaxAttemptsExceeded: 验证码尝试次数超过限制。
    NotAuthenticated: 账户未激活。
    """
    settings = get_settings()  # 获取应用配置
    repo = AuthRepo(session)  # 初始化认证仓库

    await check_account_lockout(email, session)  # 检查账户是否被锁定

    vc = await repo.get_latest_valid_code(email)  # 获取最新的有效验证码
    if not vc:
        raise InvalidCode(message="Invalid or expired verification code")  # 验证码无效或过期

    if not verify_token_hash(code, vc.code_hash):  # 验证验证码的哈希值
        attempts = await repo.increment_code_attempts(vc.id)  # 增加验证码尝试次数
        if attempts >= settings.auth.VERIFICATION_CODE_MAX_ATTEMPTS:
            await repo.invalidate_code(vc.id)  # 使验证码失效
            raise CodeMaxAttemptsExceeded(message="Maximum attempts exceeded for this code")  # 尝试次数超过限制
        await increment_login_failure(email, session)  # 增加登录失败次数
        raise InvalidCode(message="Invalid verification code")  # 验证码无效

    await repo.mark_code_used(vc.id)  # 标记验证码为已使用

    user = await repo.get_by_email(email)  # 通过电子邮件获取用户
    if not user:
        user = await repo.create_user(email)  # 如果用户不存在，则创建新用户

    if not user.is_active:
        raise NotAuthenticated(message="Account is deactivated")  # 账户未激活

    access_token = create_access_token(user.id, user.email)  # 创建访问令牌
    refresh_token_str = create_refresh_token()  # 创建刷新令牌
    refresh_token_hash = hash_token(refresh_token_str)  # 哈希刷新令牌
    # timedelta 得到两个时间相减的结果，单位是s，第二个数不传，则为0，从而达分到转秒的效果，避免手动计算 * 60
    expires_at = datetime.utcnow() + timedelta(days=settings.auth.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    await repo.create_refresh_token(user.id, refresh_token_hash, expires_at)  # 创建并存储刷新令牌

    await record_audit(
        session, operation="auth_login",
        details={"email": email},
        ip_address=client_ip, user_id=str(user.id),
        risk_level="low", status="completed",
    )  # 记录审计日志

    logger.info("user_login", user_id=user.id, email=email)  # 记录登录信息

    return {
        "access_token": access_token,  # 访问令牌
        "token_type": "Bearer",  # 令牌类型
        "expires_in": settings.auth.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # 令牌过期时间
        "user": {
            "id": user.id,  # 用户ID
            "email": user.email,  # 用户电子邮件
            "is_active": user.is_active,  # 用户是否激活
            "created_at": user.created_at.isoformat(),  # 用户创建时间
        },
        "refresh_token": refresh_token_str,  # 刷新令牌
    }


async def refresh_token(user_id: int, old_token: str, session: AsyncSession) -> dict:
    settings = get_settings()
    repo = AuthRepo(session)

    token_hash = hash_token(old_token)

    records = await repo.get_refresh_token_by_user(user_id)
    verify_result = None
    for record in records:
        is_verify = verify_token_hash(old_token, record.token_hash)
        if is_verify:
            verify_result = record
            break

    if not verify_result or verify_result.expires_at < datetime.utcnow():
        raise InvalidRefreshToken(message="Invalid or expired refresh token")

    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise InvalidRefreshToken(message="User account not found or deactivated")

    await repo.revoke_refresh_token(verify_result.id)

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
