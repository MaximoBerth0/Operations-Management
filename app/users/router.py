import logging
import uuid

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.infra.rate_limit.dependencies import rate_limit
from app.rbac.dependencies import require_permission
from app.users.dependencies import provide_user_service
from app.users.model import User
from app.users.schemas import (
    DisableUserRequest,
    UserCreateRequest,
    UserListItemResponse,
    UserReadResponse,
    UserUpdateRequest,
)
from app.users.service import UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["USERS"])


@router.post(
    "/register",
    response_model=UserReadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[rate_limit("register")],
)
async def register_user(
    data: UserCreateRequest,
    service: UserService = Depends(provide_user_service),
):
    logger.info("register endpoint called", extra={"email": data.email})
    user = await service.register_user(
        email=data.email,
        username=data.username,
        password=data.password,
    )
    logger.info("register endpoint succeeded", extra={"user_id": str(user.id)})
    return user


@router.put(
    "/me",
    response_model=UserReadResponse,
)
async def update_profile(
    data: UserUpdateRequest,
    service: UserService = Depends(provide_user_service),
    current_user: User = Depends(get_current_user),
):
    logger.info("update endpoint called", extra={"user_id": current_user.id})
    updated_user = await service.update_profile(
        current_user=current_user,
        data=data.model_dump(exclude_unset=True),  # only include fields sent in the request
    )
    logger.info("update endpoint succeeded", extra={"user_id": current_user.id})
    return updated_user 


@router.get(
    "/list",
    response_model=list[UserListItemResponse],
    dependencies=[Depends(require_permission("users:view"))],
)
async def list_users(
    service: UserService = Depends(provide_user_service),
):
    return await service.list_users()


@router.get(
    "/{user_id}",
    response_model=UserReadResponse,
    dependencies=[Depends(require_permission("users:view"))],
)
async def get_user_by_id(
    user_id: uuid.UUID,
    service: UserService = Depends(provide_user_service),
):
    return await service.get_user_by_id(user_id=user_id)


@router.get(
    "/email/{email}",
    response_model=UserReadResponse,
    dependencies=[Depends(require_permission("users:view"))],
)
async def get_user_by_email(
    email: str,
    service: UserService = Depends(provide_user_service),
):
    return await service.get_user_by_email(email=email)


@router.patch(
    "/{user_id}/disable-account",
    response_model=UserReadResponse,
    dependencies=[Depends(require_permission("users:disable"))],
)
async def disable_user(
    user_id: uuid.UUID,
    data: DisableUserRequest,
    service: UserService = Depends(provide_user_service),
    current_user: User = Depends(get_current_user),
):
    logger.info("disable_user endpoint called", extra={"user_id": current_user.id})
    disable_user = await service.disable_account(
        user_id=user_id,
        disabled_by_user_id=current_user.id,
        reason=data.reason,
    )
    logger.info("disable_user endpoint succeeded", extra={"user_id": current_user.id})
    return disable_user


@router.patch(
    "/{user_id}/enable",
    response_model=UserReadResponse,
    dependencies=[Depends(require_permission("users:enable"))],
)
async def enable_user(
    user_id: uuid.UUID,
    service: UserService = Depends(provide_user_service),
):
    logger.info("enable_user endpoint called")
    disable_user = await service.enable_account(user_id=user_id)

    logger.info("enable_user endpoint succeeded")
    return disable_user
