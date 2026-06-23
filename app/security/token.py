from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
import secrets
from app.config import get_settings


def create_access_token(user_id: int, email: str, expires_delta: timedelta | None = None) -> str:
    """
    创建访问令牌。

    参数:
    user_id (int): 用户的唯一标识符。
    email (str): 用户的电子邮件地址。
    expires_delta (timedelta | None, 可选): 令牌的过期时间间隔。如果为None，则使用默认过期时间。

    返回:
    str: 编码后的JWT访问令牌。

    异常:
    任何jwt.encode可能引发的异常，例如无效的密钥或算法。
    """
    settings = get_settings()  # 获取应用程序的配置设置
    # 计算令牌的过期时间
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.auth.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": str(user_id),  # 将用户ID作为主题
        "email": email,  # 包含用户电子邮件
        "exp": expire,  # 过期时间
        "iat": datetime.now(timezone.utc),  # 签发时间
        "type": "access",  # 令牌类型为访问令牌
    }
    private_key_path = settings.auth.JWT_PRIVATE_KEY_PATH  # 获取私钥路径
    with open(private_key_path, "r") as f:  # 打开并读取私钥文件
        private_key = f.read()
    # 使用私钥和指定算法编码JWT
    return jwt.encode(payload, private_key, algorithm=settings.auth.JWT_ALGORITHM)


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    public_key_path = settings.auth.JWT_PUBLIC_KEY_PATH
    with open(public_key_path, "r") as f:
        public_key = f.read()
    try:
        payload = jwt.decode(token, public_key, algorithms=[settings.auth.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


def create_refresh_token() -> str:
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_token_hash(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode("utf-8"), token_hash.encode("utf-8"))
