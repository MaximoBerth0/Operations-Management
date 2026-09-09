import secrets
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infra.database.base import Base
from app.orders.exceptions import (
    InvalidOrderStatus,
    InvalidQuantity,
    OrderItemNotFound,
)
from app.orders.models.enums import OrderStatus

if TYPE_CHECKING:
    from app.inventory.models.reservation import StockReservation

# code generation helper

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE_LENGTH = 8

def generate_order_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"

# Models 

class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )

    code: Mapped[str] = mapped_column(
        String(9),       # 8 chars + -
        unique=True,    
        nullable=False,
        index=True,      
    )


    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    items: Mapped[List["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    @classmethod
    def create(cls, user_id: uuid.UUID) -> "Order":
        return cls(
            user_id=user_id,
            status=OrderStatus.CREATED,
            code=generate_order_code(),
        )

    def confirm(self):
        if self.status != OrderStatus.CREATED:
            raise InvalidOrderStatus("Only created orders can be confirmed")

        self.status = OrderStatus.CONFIRMED

    def cancel(self):
        if self.status not in {
            OrderStatus.CREATED,
            OrderStatus.CONFIRMED,
        }:
            raise InvalidOrderStatus("Cannot cancel this order")

        self.status = OrderStatus.CANCELLED

    def complete(self):
        if self.status != OrderStatus.CONFIRMED:
            raise InvalidOrderStatus("Only confirmed orders can be completed")

        self.status = OrderStatus.COMPLETED

    def add_item(self, product_id: uuid.UUID, quantity: int) -> "OrderItem":
        if self.status != OrderStatus.CREATED:
            raise InvalidOrderStatus("Items can only be added to created orders")
        if quantity <= 0:
            raise InvalidQuantity("Quantity must be greater than zero")

        item = OrderItem(product_id=product_id, quantity=quantity)
        item.order = self
        return item

    def remove_item(self, product_id: uuid.UUID) -> None:
        if self.status != OrderStatus.CREATED:
            raise InvalidOrderStatus("Items can only be removed from created orders")

        for item in self.items:
            if item.product_id == product_id:
                self.items.remove(item)
                return

        raise OrderItemNotFound("Item not found in order")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid7,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id"),
        nullable=False,
        index=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("inventory_products.id"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    order: Mapped["Order"] = relationship(
        back_populates="items",
    )
    reservation: Mapped[Optional["StockReservation"]] = relationship(
        back_populates="order_item",
        uselist=False,
    )
