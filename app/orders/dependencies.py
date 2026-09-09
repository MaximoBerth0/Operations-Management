from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database.session import get_session
from app.inventory.dependencies import provide_inventory_service
from app.inventory.service import InventoryService
from app.orders.repository import OrderRepository
from app.orders.service import OrderService


def get_order_service(
    db: AsyncSession = Depends(get_session),
    inventory_service: InventoryService = Depends(provide_inventory_service),
) -> OrderService:
    return OrderService(
        db=db,
        order_repo=OrderRepository(db),
        inventory_service=inventory_service,
    )
