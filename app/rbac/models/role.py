import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database.base import Base
from app.rbac.models.role_permission import role_permissions
from app.rbac.models.user_role import user_roles

if TYPE_CHECKING:
    from app.rbac.models.permission import Permission
    from app.users.model import User


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255))

    permissions: Mapped[List["Permission"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
    )
    users: Mapped[List["User"]] = relationship(
        secondary=user_roles,
        back_populates="roles",
    )
