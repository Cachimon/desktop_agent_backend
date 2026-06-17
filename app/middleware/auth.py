from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.security.token import verify_access_token
from app.utils.exceptions import CSRFValidationFailed, NotAuthenticated

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    if not credentials:
        raise NotAuthenticated(message="Authentication required")
    try:
        payload = verify_access_token(credentials.credentials)
        return payload
    except ValueError as e:
        raise NotAuthenticated(message=str(e))


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    if not credentials:
        return None
    try:
        return verify_access_token(credentials.credentials)
    except ValueError:
        return None


async def validate_csrf(request: Request) -> None:
    x_requested_with = request.headers.get("X-Requested-With")
    if not x_requested_with:
        raise CSRFValidationFailed(message="CSRF validation failed: missing X-Requested-With header")
