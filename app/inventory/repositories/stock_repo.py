import uuid
from typing import Optional

from app.inventory.models.reservation import StockReservation
from app.inventory.models.stock import InventoryStock, StockMovement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


class StockRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    # inventory

    async def get_stock(self, stock_id: uuid.UUID) -> InventoryStock | None:
        stmt = select(InventoryStock).where(InventoryStock.id == stock_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def location_has_stock(self, location_id: uuid.UUID) -> bool:
        stmt = select(InventoryStock.id).where(
            InventoryStock.location_id == location_id
        ).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_stock_by_location_and_product_for_update(
        self, product_id: uuid.UUID, location_id: uuid.UUID
    ) -> InventoryStock | None:
        stmt = (
            select(InventoryStock)
            .where(
                InventoryStock.product_id == product_id,
                InventoryStock.location_id == location_id,
            )
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_stock_by_id_for_update(
        self, stock_id: uuid.UUID
    ) -> InventoryStock | None:
        stmt = (
            select(InventoryStock)
            .where(InventoryStock.id == stock_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reservation_by_id(
        self, reservation_id: uuid.UUID
    ) -> StockReservation | None:
        stmt = select(StockReservation).where(
            StockReservation.id == reservation_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_reservation_by_id_for_update(
        self, reservation_id: uuid.UUID
    ) -> StockReservation | None:
        stmt = (
            select(StockReservation)
            .where(StockReservation.id == reservation_id)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_available_stock_by_product(
        self, product_id: uuid.UUID
    ) -> InventoryStock | None:
        stmt = select(InventoryStock).where(InventoryStock.product_id == product_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def initialize_stock(
        self, location_id: uuid.UUID, product_id: uuid.UUID, quantity: int, reorder_point: int
    ) -> InventoryStock:
        stock = InventoryStock(
            location_id=location_id,
            product_id=product_id,
            quantity=quantity,
            reorder_point=reorder_point,
        )
        self.db.add(stock)
        await self.db.commit()
        await self.db.refresh(stock)
        return stock

    async def update_quantity_stock(self, stock: InventoryStock) -> InventoryStock:
        await self.db.commit()
        await self.db.refresh(stock)
        return stock

    async def create_movement(self, movement: StockMovement) -> StockMovement:
        self.db.add(movement)
        await self.db.commit()
        await self.db.refresh(movement)
        return movement

    async def list_stock_movements(
        self, stock_id: uuid.UUID, limit: int = 100
    ) -> list[StockMovement]:
        stmt = (
            select(StockMovement)
            .where(StockMovement.stock_id == stock_id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_stock_levels(
        self,
        location_id: Optional[uuid.UUID] = None,
        product_id: Optional[uuid.UUID] = None,
    ) -> list[InventoryStock]:

        stmt = select(InventoryStock)

        if location_id:
            stmt = stmt.where(InventoryStock.location_id == location_id)
        if product_id:
            stmt = stmt.where(InventoryStock.product_id == product_id)

        # load relationships with selecinload to avoid N+1
        stmt = stmt.options(
            selectinload(InventoryStock.product), selectinload(InventoryStock.location)
        )

        stmt = stmt.order_by(InventoryStock.product_id, InventoryStock.location_id)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_available_stock(self, stock_id: uuid.UUID) -> int | None:
        stmt = select(InventoryStock.quantity - InventoryStock.reserved_quantity).where(
            InventoryStock.id == stock_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
