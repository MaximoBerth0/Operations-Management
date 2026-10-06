import logging
import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.inventory.dependencies import get_current_location
from app.inventory.models.location import Location
from app.orders.dependencies import get_order_service
from app.orders.schemas import AddItemRequest, OrderResponse
from app.orders.service import OrderService
from app.rbac.dependencies import require_permission
from app.users.model import User

"""
GET  /orders/me                          - list current user's own orders
POST /orders                             - create order
POST /orders/{id}/items                  - add item to order
DELETE /orders/{id}/items/{item_id}      - remove item from order

# state transitions
PATCH /orders/{id}/confirm               - confirm order
PATCH /orders/{id}/cancel                - cancel order
PATCH /orders/{id}/complete              - complete order
"""

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["ORDERS"])

# orders

@router.get(
    "/code/{code}",
    response_model=OrderResponse,
)
async def get_order_by_code(
    code: str,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info("get_order_by_code endpoint called")
    order = await service.get_order_by_code(code)
    logger.info("get_order_by_code endpoint succeeded", extra={"order_id": order.id})
    return order


@router.get(
    "/me",
    response_model=list[OrderResponse],
)
async def list_my_orders(
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> Sequence[OrderResponse]:

    logger.info("list_my_orders endpoint called", extra={"user_id": current_user.id})
    orders = await service.list_user_orders(user_id=current_user.id)
    logger.info(
        "list_my_orders endpoint succeeded",
        extra={"user_id": current_user.id, "count": len(orders)},
    )
    return orders


@router.post(
    "/",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("order:create"))],
)
async def create_order(
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info("create_order endpoint called", extra={"user_id": current_user.id})
    order = await service.create_order(user_id=current_user.id)
    logger.info("create_order endpoint succeeded", extra={"order_id": order.id})
    return order


@router.post(
    "/{id}/items",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permission("order:add"))],
)
async def add_item_to_order(
    id: uuid.UUID,
    payload: AddItemRequest,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info(
        "add_item_to_order endpoint called",
        extra={"order_id": id, "product_id": payload.product_id},
    )
    order = await service.add_item_to_order(
        order_id=id,
        product_id=payload.product_id,
        quantity=payload.quantity,
    )
    logger.info("add_item_to_order endpoint succeeded", extra={"order_id": id})
    return order


@router.delete(
    "/{order_id}/items/{product_id}",
    response_model=OrderResponse,
    dependencies=[Depends(require_permission("order:remove"))],
)
async def remove_item_from_order(
    order_id: uuid.UUID,
    product_id: uuid.UUID,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info(
        "remove_item_from_order endpoint called",
        extra={"order_id": order_id, "product_id": product_id},
    )
    order = await service.remove_item_from_order(
        order_id=order_id,
        product_id=product_id,
    )
    logger.info("remove_item_from_order endpoint succeeded", extra={"order_id": order_id})
    return order


# state transitions


@router.patch(
    "/{id}/confirm",
    response_model=OrderResponse,
    dependencies=[Depends(require_permission("order:confirm"))],
)
async def confirm_order(
    id: uuid.UUID,
    location: Location = Depends(get_current_location),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info(
        "confirm_order endpoint called",
        extra={"order_id": id, "location_id": location.id},
    )
    order = await service.confirm_order(
        order_id=id,
        location_id=location.id,
    )
    logger.info("confirm_order endpoint succeeded", extra={"order_id": id})
    return order


@router.patch(
    "/{id}/cancel",
    response_model=OrderResponse,
    dependencies=[Depends(require_permission("order:cancel"))],
)
async def cancel_order(
    id: uuid.UUID,
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info("cancel_order endpoint called", extra={"order_id": id})
    order = await service.cancel_order(order_id=id)
    logger.info("cancel_order endpoint succeeded", extra={"order_id": id})
    return order


@router.patch(
    "/{id}/complete",
    response_model=OrderResponse,
    dependencies=[Depends(require_permission("order:complete"))],
)
async def complete_order(
    id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: OrderService = Depends(get_order_service),
) -> OrderResponse:
    logger.info("complete_order endpoint called", extra={"order_id": id, "user_id": current_user.id})
    order = await service.complete_order(order_id=id, user_id=current_user.id)
    logger.info("complete_order endpoint succeeded", extra={"order_id": id})
    return order
