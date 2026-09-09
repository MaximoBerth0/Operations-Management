import uuid

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.database.session import get_session
from app.inventory.models.location import Location
from app.inventory.repositories.category_repo import CategoryRepository
from app.inventory.repositories.location_repo import LocationRepository
from app.inventory.repositories.product_repo import ProductRepository
from app.inventory.repositories.reservation_repo import ReservationRepository
from app.inventory.repositories.stock_repo import StockRepository
from app.inventory.service import InventoryService


def provide_inventory_service(
    db: AsyncSession = Depends(get_session),
) -> InventoryService:
    return InventoryService(
        stock_repo=StockRepository(db),
        product_repo=ProductRepository(db),
        category_repo=CategoryRepository(db),
        location_repo=LocationRepository(db),
        reservation_repo=ReservationRepository(db),
    )


async def get_current_location(
    x_location_id: uuid.UUID | None = Header(default=None),
    db: AsyncSession = Depends(get_session),
) -> Location:
    if x_location_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing X-Location-Id header",
        )

    location_repo = LocationRepository(db)
    location = await location_repo.get_location(x_location_id)

    if location is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location not found",
        )

    return location
