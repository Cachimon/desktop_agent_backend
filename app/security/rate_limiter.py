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
    """
    检查发送验证码的频率限制。

    参数:
    email (str): 用户的电子邮件地址。
    session (AsyncSession): 数据库异步会话。

    异常:
    RateLimitExceeded: 如果发送验证码的频率超过了限制，将引发此异常。

    """
    # TODO: 把“检查”和“计数”分离得太开，中间留出了巨大的时间窗口供并发请求穿透。建议使用 Redis 的 INCR + EXPIRE 命令来实现原子性的限流检查。
    # 获取应用程序的设置
    settings = get_settings()
    # 创建认证仓库实例
    repo = AuthRepo(session)

    # 获取指定邮箱的发送验证码频率限制信息
    rl = await repo.get_rate_limit(email, "send_code")
    # 获取当前时间
    now = datetime.utcnow()

    # 如果存在频率限制记录且记录有窗口开始时间
    if rl and rl.window_start:
        # 计算从窗口开始到现在的秒数
        elapsed = (now - rl.window_start).total_seconds()
        # 如果经过的时间小于设定的冷却时间且尝试次数大于0
        # FIX: 去掉 and rl.attempt_count > 0 的条件限制，rl.attempt_count必然>=1
        if elapsed < settings.auth.SEND_CODE_COOLDOWN_SECONDS:
            # 计算剩余的冷却时间
            remaining = int(settings.auth.SEND_CODE_COOLDOWN_SECONDS - elapsed)
            # 引发频率限制异常，提示用户剩余的等待时间
            raise RateLimitExceeded(
                message=f"Please wait {remaining}s before requesting a new code",
                detail={"remaining_seconds": remaining},
            )

    # 统计今天已经发送的验证码数量
    daily_count = await repo.count_codes_sent_today(email)
    # 如果今天的发送数量超过了每日限制
    if daily_count >= settings.auth.SEND_CODE_DAILY_LIMIT:
        # 引发频率限制异常，提示用户每日发送验证码的限制
        raise RateLimitExceeded(
            message="Daily verification code limit exceeded",
            detail={"daily_limit": settings.auth.SEND_CODE_DAILY_LIMIT},
        )


async def check_ip_rate_limit(ip_address: str, session: AsyncSession) -> None:
    """
    检查指定IP地址的请求速率是否超过限制。采用“固定窗口”算法：先记录请求，再检查是否超限。

    参数:
        ip_address (str): 要检查的IP地址。
        session (AsyncSession): 数据库会话对象。

    异常:
        IPRateLimitExceeded: 如果IP请求速率超过每分钟限制，将引发此异常。
    """
    # FIX：原先的逻辑只有新增，没有插入的逻辑。修改这个逻辑，存储的window_start改为当前分钟的初始秒

    settings = get_settings()
    repo = AuthRepo(session)

    # 1. 计算当前时间窗口的起始时间（对齐到分钟）
    # 例如：2023-10-01 12:00:35 -> 2023-10-01 12:00:00
    # 这样保证在 12:00:00 到 12:00:59 期间，所有请求的 window_start 都是一致的
    now = datetime.utcnow()
    window_start = now.replace(second=0, microsecond=0)

    # 2. 【先记账】更新或插入速率限制记录
    # 这一步会自动处理：
    # - 如果是当前窗口：计数 +1
    # - 如果是新窗口或无记录：重置计数为 1
    rl = await repo.upsert_rate_limit(ip_address, "global_request", window_start)

    # 3. 【后查账】检查是否超限
    # 注意：因为 upsert 已经把当前这次请求算进去了，
    # 所以如果限制是 10 次，当 count 变成 11 时，就应该拦截
    if rl.attempt_count > settings.auth.IP_RATE_LIMIT_PER_MINUTE:
        raise IPRateLimitExceeded(
            message="IP rate limit exceeded",
            detail={
                "limit": settings.auth.IP_RATE_LIMIT_PER_MINUTE,
                "window": "60s",
                "current_count": rl.attempt_count,  # 可以在异常中附带当前计数，方便调试
            },
        )


async def check_account_lockout(email: str, session: AsyncSession) -> None:
    """
    检查指定邮箱的账户是否因为登录失败而被锁定。

    参数:
    email (str): 需要检查的邮箱地址。
    session (AsyncSession): 数据库异步会话。

    返回值:
    None: 无返回值，但当账户被锁定时会引发 AccountLocked 异常。

    异常:
    AccountLocked: 如果账户因登录失败次数过多而被锁定，则抛出此异常。
    """
    settings = get_settings()  # 获取应用配置设置
    repo = AuthRepo(session)  # 初始化认证仓库实例

    rl = await repo.get_rate_limit(email, "login_failure")  # 获取指定邮箱的登录失败频率限制信息
    now = datetime.utcnow()  # 获取当前时间（UTC）

    if rl and rl.window_start:  # 如果存在频率限制记录和起始时间窗口
        elapsed = (now - rl.window_start).total_seconds()  # 计算从起始时间到现在的秒数
        # 计算锁定时长（秒）
        lockout_seconds = settings.auth.LOGIN_FAILURE_LOCKOUT_DURATION_MINUTES * 60
        # 如果登录失败次数超过阈值
        if rl.attempt_count >= settings.auth.LOGIN_FAILURE_LOCKOUT_THRESHOLD:
            if elapsed < lockout_seconds:  # 如果经过的时间小于锁定时长
                remaining = int(lockout_seconds - elapsed)  # 计算剩余锁定时间（秒）
                raise AccountLocked(  # 抛出账户被锁定的异常
                    message=f"Account locked for {remaining}s",
                    detail={"remaining_seconds": remaining},
                )
            else:
                await repo.reset_rate_limit(email, "login_failure")  # 重置登录失败计数


async def check_ip_anomaly(ip_address: str, session: AsyncSession) -> None:
    """
    异步检查指定IP地址的异常邮件活动。

    参数:
    ip_address (str): 要检查的IP地址。
    session (AsyncSession): 异步数据库会话。

    异常:
    AnomalousIPDetected: 如果在设定的时间窗口内，来自该IP的邮件数量超过阈值，则抛出此异常。

    返回:
    None
    """
    # 获取应用程序的设置
    settings = get_settings()
    # 创建认证仓库实例，用于与数据库交互
    repo = AuthRepo(session)

    # 统计在设定时间窗口内来自指定IP的邮件数量
    count = await repo.count_emails_for_ip(
        ip_address, window_hours=settings.auth.IP_ANOMALY_WINDOW_HOURS
    )
    # 如果邮件数量超过异常检测阈值，则抛出异常
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
