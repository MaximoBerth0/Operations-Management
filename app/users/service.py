import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.security.passwords import hash_password
from app.users.exceptions import UserAlreadyExists, UserNotFound
from app.users.model import User
from app.users.repository import UserRepository

logger = logging.getLogger(__name__)

class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = UserRepository(session)

    async def register_user(self, email: str, username: str, password: str) -> User:
        existing = await self.repo.get_by_email(email)
        if existing:
            logger.warning("user registration failed", extra={"email": email})
            raise UserAlreadyExists("User with this email already exists")
        user = User(
            email=email,
            username=username,
            hashed_password=hash_password(password),
        )
        await self.repo.create_user(user)
        logger.info("registered user", extra={"user_id": str(user.id), "email": email})
        return user
    
    async def update_profile(self, current_user: User, data: dict) -> User:
        if not data:
            logger.debug("update_profile called with empty data", extra={"user_id": str(current_user.id)})
            return current_user
        forbidden_fields = {
            "id",
            "is_active",
            "created_at",
            "updated_at",
            # is_active is derived from these, so they must not be self-editable
            "disabled_at",
            "disabled_by",
            "reason",
        }
        safe_data = {k: v for k, v in data.items() if k not in forbidden_fields}
        if not safe_data:
            logger.warning("update_profile: all fields were forbidden", extra={"user_id": str(current_user.id), "attempted_fields": list(data.keys())})
            return current_user

        updated_user = await self.repo.update_profile(user=current_user, data=safe_data)
        logger.info("user profile updated", extra={"user_id": str(current_user.id), "updated_fields": list(safe_data.keys())})
        return updated_user
        
    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        limit = min(limit, 100)

        users = await self.repo.list_users(
            skip=skip,
            limit=limit,
        )

        return list(users)

    async def get_user_by_id(
        self,
        user_id: uuid.UUID,
    ) -> User:
        user = await self.repo.get_by_id(user_id)
        if not user:
            logger.warning("get_user_by_id: user not found", extra={"user_id": user_id})
            raise UserNotFound("User not found")

        return user

    async def get_user_by_email(
        self,
        email: str,
    ) -> User:
        user = await self.repo.get_by_email(email)
        if not user:
            logger.warning("get_user_by_email: user not found", extra={"user_email": email})
            raise UserNotFound("User not found")

        return user

    async def enable_account(self, user_id: uuid.UUID) -> User:
        user = await self.repo.get_by_id(user_id)
        if not user:
            logger.warning("enable_account: user not found", extra={"user_id": user_id})
            raise UserNotFound("User not found")

        user.disabled_at = None
        user.disabled_by = None
        user.reason = None

        updated_user = await self.repo.enable_account(user)
        logger.info("account enabled", extra={"user_id": user_id})
        return updated_user

    async def disable_account(
        self, user_id: uuid.UUID, disabled_by_user_id: uuid.UUID, reason: str
    ) -> User:
        user = await self.repo.get_by_id(user_id)
        if not user:
            logger.warning("disable_account: user not found", extra={"user_id": user_id})
            raise UserNotFound("User not found")

        user.disabled_at = datetime.now(timezone.utc)
        user.disabled_by = disabled_by_user_id
        user.reason = reason

        updated_user = await self.repo.disable_account(user)
        logger.info("account disabled", extra={"user_id": user_id})
        return updated_user