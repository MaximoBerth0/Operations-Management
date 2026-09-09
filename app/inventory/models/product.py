from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database.base import Base
from app.inventory.models.category import product_category

if TYPE_CHECKING:
    from app.inventory.models.category import Category
    from app.inventory.models.stock import InventoryStock


class Product(Base):
    __tablename__ = "inventory_products"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    categories: Mapped[list["Category"]] = relationship(
        secondary=product_category,
        back_populates="products",
    )
    stocks: Mapped[list["InventoryStock"]] = relationship(back_populates="product")
