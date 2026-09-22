import logging
import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.inventory.service import InventoryService
from app.orders.exceptions import InvalidOrderStatus, OrderNotFound
from app.orders.models.enums import OrderStatus
from app.orders.models.order import Order
from app.orders.repository import OrderRepository

"""
create_order()
add_item_to_order()
remove_item_from_order()
confirm_order()
cancel_order()
complete_order()
"""

logger = logging.getLogger(__name__)

_CODE_LENGTH = 8

def _normalize_code(value: str) -> str | None:
    """
    Returns ``None`` when the input can't be a valid code so the caller can
    reject it without hitting the database.
    """
    cleaned = value.strip().upper().replace("-", "").replace(" ", "")
    if len(cleaned) != _CODE_LENGTH:
        return None
    return f"{cleaned[:4]}-{cleaned[4:]}"


class OrderService:
    def __init__(
        self,
        db: AsyncSession,
        order_repo: OrderRepository,
        inventory_service: InventoryService,
    ):
        self.db = db
        self.order_repo = order_repo
        self.inventory_service = inventory_service

    async def create_order(self, user_id: uuid.UUID) -> Order:

        result = await self.order_repo.create_order(user_id)

        logger.info("create_order: order created", extra={"order_id": result.id})
        return result
    
    # public endpoint 

    async def list_user_orders(self, user_id: uuid.UUID) -> Sequence[Order]:
        orders = await self.order_repo.list_orders_by_user(user_id)
        logger.info(
            "list_user_orders: orders fetched",
            extra={"user_id": user_id, "count": len(orders)},
        )
        return orders

    async def get_order_by_code(self, code: str) -> Order:
        normalized = _normalize_code(code)
        if normalized is None:
            logger.warning("get_order_by_code: malformed code")
            raise OrderNotFound()

        order = await self.order_repo.get_order_by_code(normalized)
        if order is None:
            logger.warning("get_order_by_code: order not found")
            raise OrderNotFound()

        logger.info("get_order_by_code: order fetched", extra={"order_id": order.id})
        return order

    async def add_item_to_order(
        self, order_id: uuid.UUID, product_id: uuid.UUID, quantity: int
    ) -> Order:
        # validate the product exists before touching the order
        await self.inventory_service.get_product(product_id)
        order = await self.order_repo.append_item(order_id, product_id, quantity)
        if order is None:
            logger.warning("add_item_to_order: order not found", extra={"order_id": order_id})
            raise OrderNotFound()
        logger.info("add_item_to_order: item added", extra={"order_id": order_id, "product_id": product_id})
        return order

    async def remove_item_from_order(self, order_id: uuid.UUID, product_id: uuid.UUID) -> Order:
        order = await self.order_repo.remove_item(order_id, product_id)
        if order is None:
            logger.warning("remove_item_from_order: order not found", extra={"order_id": order_id})
            raise OrderNotFound()
        logger.info("remove_item_from_order: item removed", extra={"order_id": order_id, "product_id": product_id})
        return order
    
    async def confirm_order(self, order_id: uuid.UUID, location_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_order(order_id)
        if order is None:
            logger.warning("confirm_order: order not found", extra={"order_id": order_id})
            raise OrderNotFound()
        if order.status != OrderStatus.CREATED:
            logger.warning("confirm_order: wrong status order, should be CREATED", extra={"invalid_status": order.status})
            raise InvalidOrderStatus()
        for item in order.items:
            await self.inventory_service.reserve_for_item(
                order_item_id=item.id,
                product_id=item.product_id,
                location_id=location_id,
                quantity=item.quantity,
            )

        order.status = OrderStatus.CONFIRMED
        await self.db.commit()

        logger.info("confirm_order: order confirmed", extra={"order_id": order_id, "location_id": location_id})
        return order

    async def cancel_order(self, order_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_order(order_id)
        if order is None:
            logger.warning("cancel_order: order not found", extra={"order_id": order_id})
            raise OrderNotFound()

        if order.status != OrderStatus.CONFIRMED:
            logger.warning("cancel_order: wrong status order, should be CONFIRMED", extra={"order_id": order_id, "invalid_status": order.status})
            raise InvalidOrderStatus()

        for item in order.items:
            if item.reservation is not None:
                await self.inventory_service.release_for_item(
                    item.reservation.id
                )
        order.cancel()
        await self.db.commit()
        logger.info("cancel_order: order cancelled", extra={"order_id": order_id})
        return order

    async def complete_order(self, order_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_order(order_id)
        if order is None:
            logger.warning("complete_order: order not found", extra={"order_id": order_id})
            raise OrderNotFound()
        if order.status != OrderStatus.CONFIRMED:
            logger.warning("complete_order: wrong status order, should be CONFIRMED", extra={"order_id": order_id, "invalid_status": order.status})
            raise InvalidOrderStatus()

        for item in order.items:
            if item.reservation is not None:
                await self.inventory_service.fulfill_for_item(
                    item.reservation.id
                )

        order.complete()
        await self.db.commit()
        logger.info("complete_order: order completed", extra={"order_id": order_id})
        return order
