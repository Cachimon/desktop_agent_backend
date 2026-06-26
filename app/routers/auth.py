from fastapi import APIRouter, Depends, Request, Response, Body
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.auth import get_current_user, validate_csrf
from app.models.base import get_db_session
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    SendCodeRequest,
    TokenResponse,
)
from app.services import auth_service
from app.utils.exceptions import InvalidRefreshToken

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/send-code")
async def send_code(
    body: SendCodeRequest,
    request: Request,
    _csrf: None = Depends(validate_csrf),
    session: AsyncSession = Depends(get_db_session),
):
    client_ip = request.client.host if request.client else "unknown"
    result = await auth_service.send_verification_code(body.email, client_ip, session)
    return result


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    _csrf: None = Depends(validate_csrf),
    session: AsyncSession = Depends(get_db_session),
):
    client_ip = request.client.host if request.client else "unknown"
    result = await auth_service.login(body.email, body.code, client_ip, session)

    refresh_token = result.pop("refresh_token")
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        # secure=True,
        samesite="strict",
        path="/api/v1/auth",
        max_age=7 * 24 * 3600,
    )
    return result


@router.post("/refresh")
async def refresh(
    request: Request,
    response: Response,
    user_id: int = Body(embed=True),
    _csrf: None = Depends(validate_csrf),
    session: AsyncSession = Depends(get_db_session),
):
    refresh_token_str = request.cookies.get("refresh_token")
    if not refresh_token_str:
        raise InvalidRefreshToken(message="No refresh token provided")

    try:
        result = await auth_service.refresh_token(user_id, refresh_token_str, session)
    except InvalidRefreshToken:
        try:
            await auth_service.detect_token_reuse(refresh_token_str, session)
        except Exception:
            pass
        raise

    new_refresh_token = result.pop("refresh_token")
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        # secure=True,
        samesite="strict",
        path="/api/v1/auth",
        max_age=7 * 24 * 3600,
    )
    return result


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    _csrf: None = Depends(validate_csrf),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    refresh_token_str = request.cookies.get("refresh_token")
    await auth_service.logout(int(user["sub"]), refresh_token_str, session)
    response.delete_cookie(key="refresh_token", path="/api/v1/auth")
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    return await auth_service.get_current_user_info(int(user["sub"]), session)
