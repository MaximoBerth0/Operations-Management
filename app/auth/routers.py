import logging

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.schemas import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokensRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.auth.service import AuthService
from app.infra.rate_limit.dependencies import rate_limit
from app.users.model import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["AUTH"])


@router.post("/login", response_model=TokenResponse, dependencies=[rate_limit("login")])
async def login(
    data: LoginRequest,
    service: AuthService = Depends(get_auth_service),
):
    logger.info("login endpoint called", extra={"email": data.email})
    tokens = await service.login(data.email, data.password)
    logger.info("login endpoint succeeded", extra={"email": data.email})
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[rate_limit("token_refresh")],
)
async def refresh_tokens(
    data: RefreshTokensRequest,
    service: AuthService = Depends(get_auth_service),
):
    logger.info("refresh endpoint called")
    tokens = await service.refresh_session(data.refresh_token)
    logger.info("refresh endpoint succeeded")
    return tokens


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    data: LogoutRequest,
    service: AuthService = Depends(get_auth_service),
):
    logger.info("logout endpoint called")
    await service.logout(data.refresh_token)
    logger.info("logout endpoint succeeded")


@router.post(
    "/forgot",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[rate_limit("password_reset")],
)
async def forgot_password(
    data: ForgotPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    logger.info("forgot_password endpoint called", extra={"email": data.email})
    await service.forgot_password(data.email)
    logger.info("forgot_password endpoint succeeded", extra={"email": data.email})


@router.post(
    "/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[rate_limit("password_reset")],
)
async def reset_password(
    data: ResetPasswordRequest,
    service: AuthService = Depends(get_auth_service),
):
    logger.info("reset_password endpoint called")
    await service.reset_password(data.token, data.new_password)
    logger.info("reset_password endpoint succeeded")


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    logger.info("change_password endpoint called", extra={"user_id": current_user.id})
    await service.change_password(
        current_user,
        data.old_password,
        data.new_password,
    )
    logger.info("change_password endpoint succeeded", extra={"user_id": current_user.id})
