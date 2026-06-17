from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def create_access_token(user_id: int, email: str, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.auth.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    private_key_path = settings.auth.JWT_PRIVATE_KEY_PATH
    with open(private_key_path, "r") as f:
        private_key = f.read()
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
    import secrets
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    return bcrypt.hashpw(token.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_token_hash(token: str, token_hash: str) -> bool:
    return bcrypt.checkpw(token.encode("utf-8"), token_hash.encode("utf-8"))
