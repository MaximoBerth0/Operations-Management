from app.common.constants.inventory_permissions import INVENTORY_PERMISSIONS
from app.common.constants.order_permissions import ORDER_PERMISSIONS
from app.common.constants.system_permissions import SYSTEM_PERMISSIONS
from app.common.constants.user_permissions import USER_PERMISSIONS
from app.infra.database.session import get_script_session
from app.rbac.models.permission import Permission
from app.rbac.repositories.permission_repo import PermissionRepository

ALL_PERMISSIONS = set(
    SYSTEM_PERMISSIONS + INVENTORY_PERMISSIONS + USER_PERMISSIONS + ORDER_PERMISSIONS
)


async def seed_permissions() -> None:
    async with get_script_session() as session:
        repo = PermissionRepository(session)

        for code in ALL_PERMISSIONS:
            existing = await repo.get_by_code(code)
            if existing:
                continue

            await repo.create(
                Permission(
                    code=code,
                    name=code,
                    description=f"Permission: {code}",
                )
            )
