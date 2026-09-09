from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database.base import Base

if TYPE_CHECKING:
    from app.inventory.models.stock import InventoryStock


class Location(Base):
    __tablename__ = "inventory_location"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(255))

    stocks: Mapped[list["InventoryStock"]] = relationship(back_populates="location")
