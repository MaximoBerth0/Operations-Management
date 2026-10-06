import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rbac.models.permission import Permission
from app.rbac.models.role_permission import role_permissions
from app.rbac.models.user_role import user_roles
from app.users.model import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_emails_with_permission(self, code: str) -> list[str]:
        """Emails of active users holding the permission through any of their roles."""
        stmt = (
            select(User.email)
            .join(user_roles, user_roles.c.user_id == User.id)
            .join(role_permissions, role_permissions.c.role_id == user_roles.c.role_id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(Permission.code == code, User.disabled_at.is_(None))
            .distinct()
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_users(self, skip: int = 0, limit: int = 100) -> Sequence[User]:
        stmt = select(User).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def enable_account(self, user: User) -> User:
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def disable_account(self, user: User) -> User:
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def create_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def save_user(self, user: User) -> User:
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update_profile(self, user: User, data: dict) -> User:
        for field, value in data.items():
            if hasattr(user, field):
                setattr(user, field, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user
