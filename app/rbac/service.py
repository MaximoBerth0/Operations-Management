import uuid

from app.rbac.exceptions import (
    PermissionAlreadyAssigned,
    PermissionDenied,
    PermissionNotFound,
    RoleAlreadyAssignedToUser,
    RoleAlreadyExists,
    RoleNotFound,
    RolePermissionNotFound,
    UserRoleNotFound,
)
from app.rbac.models.role import Role
from app.rbac.repositories.permission_repo import PermissionRepository
from app.rbac.repositories.role_repo import RoleRepository


class RBACService:
    def __init__(
        self,
        role_repo: RoleRepository,
        permission_repo: PermissionRepository,
    ):
        self.role_repo = role_repo
        self.permission_repo = permission_repo

    # Roles
    async def create_role(self, name: str, description: str | None = None) -> Role:
        if await self.role_repo.get_by_name(name):
            raise RoleAlreadyExists()

        role = Role(name=name, description=description)
        await self.role_repo.create(role)
        return role

    async def update_role(
        self,
        role_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Role:
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise RoleNotFound()

        if name:
            existing = await self.role_repo.get_by_name(name)
            if existing and existing.id != role_id:
                raise RoleAlreadyExists()
            role.name = name

        if description is not None:
            role.description = description

        return role

    async def list_roles(self) -> list[Role]:
        roles = await self.role_repo.get_all()
        return roles

    # Role-User
    async def assign_role_to_user(self, user_id: uuid.UUID, role_id: uuid.UUID):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise RoleNotFound()

        if await self.role_repo.user_has_role(user_id, role_id):
            raise RoleAlreadyAssignedToUser()

        await self.role_repo.add_role_to_user(user_id, role_id)

    async def remove_role_from_user(self, user_id, role_id) -> None:
        if not await self.role_repo.user_has_role(user_id, role_id):
            raise UserRoleNotFound()

        await self.role_repo.remove_role_from_user(user_id, role_id)

    # Role-Permission
    async def add_permission_to_role(self, role_id: uuid.UUID, permission_id: uuid.UUID):
        role = await self.role_repo.get_by_id(role_id)
        if not role:
            raise RoleNotFound()

        permission = await self.permission_repo.get_by_id(permission_id)
        if not permission:
            raise PermissionNotFound()

        if await self.role_repo.role_has_permission(role_id, permission_id):
            raise PermissionAlreadyAssigned()

        await self.role_repo.add_permission_to_role(role_id, permission_id)

    async def remove_permission_from_role(
        self, role_id: uuid.UUID, permission_id: uuid.UUID) -> None:

        if not await self.role_repo.role_has_permission(role_id, permission_id):
            raise RolePermissionNotFound()

        await self.role_repo.remove_permission_from_role(role_id, permission_id)

    # permission checks
    async def get_user_permissions(self, user_id: uuid.UUID) -> set[str]:
        user = await self.role_repo.get_user_with_roles_and_permissions(user_id)
        if not user:
            return set()
        return {
            permission.code for role in user.roles for permission in role.permissions
        }

    async def ensure_permission(self, user_id: uuid.UUID, permission_code: str) -> None:
        user = await self.role_repo.get_user_with_roles_and_permissions(user_id)
        if not user:
            raise PermissionDenied()

        has_permission = any(
            permission.code == permission_code
            for role in user.roles
            for permission in role.permissions
        )

        if not has_permission:
            raise PermissionDenied()