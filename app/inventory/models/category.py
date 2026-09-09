from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Column, ForeignKey, String, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database.base import Base

if TYPE_CHECKING:
    from app.inventory.models.product import Product

product_category = Table(
    "inventory_product_categories",
    Base.metadata,
    Column("product_id", Uuid, ForeignKey("inventory_products.id"), primary_key=True),
    Column("category_id", Uuid, ForeignKey("inventory_categories.id"), primary_key=True),
)


class Category(Base):
    __tablename__ = "inventory_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    products: Mapped[list["Product"]] = relationship(
        secondary=product_category,
        back_populates="categories",
    )
