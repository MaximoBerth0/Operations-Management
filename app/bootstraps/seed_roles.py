from app.common.constants.system_roles import SYSTEM_ROLES
from app.infra.database.session import get_script_session
from app.rbac.repositories.permission_repo import PermissionRepository
from app.rbac.repositories.role_repo import RoleRepository


async def seed_roles() -> None:
    async with get_script_session() as session:
        role_repo = RoleRepository(session)
        perm_repo = PermissionRepository(session)

        for role_name, permission_codes in SYSTEM_ROLES.items():
            role = await role_repo.get_or_create(
                name=role_name,
                is_system=True,
            )

            for code in permission_codes:
                perm = await perm_repo.get_by_code(code)
                if not perm:
                    continue

                if await role_repo.role_has_permission(role.id, perm.id):
                    continue

                await role_repo.add_permission_to_role(role.id, perm.id)
