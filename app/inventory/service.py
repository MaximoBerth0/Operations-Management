"""
PRODUCT:
  get_product()
  list_products()
  create_product()
  update_product()
  activate_product()
  deactivate_product()

CATEGORY:
  create_category()
  remove_category()
  add_product_to_category()
  remove_product_from_category

STOCK:
  initialize_stock()
  add_stock()
  remove_stock()
  adjust_stock()
  list_stock_movements()
  get_stock_levels()

LOCATION:
  get_location_list()
  get_location()
  create_location()
  update_location()
  delete_location()

RESERVATION:
  reserve_for_item()
  release_for_item()
  fulfill_for_item()

"""
import logging
import uuid
from typing import Optional

from app.inventory.exceptions import (
    CategoryAlreadyExists,
    CategoryDescriptionIsRequired,
    CategoryNameIsRequired,
    CategoryNotFound,
    InsufficientStock,
    InvalidLocation,
    InvalidProductOrLocation,
    InvalidQuantityStock,
    InvalidReservationStatus,
    LocationAddressIsRequired,
    LocationAlreadyExists,
    LocationCityIsRequired,
    LocationHasStock,
    LocationNameIsRequired,
    LocationNotFound,
    NoParametersProvide,
    ProductAlreadyExits,
    ProductNameIsRequired,
    ProductNotFound,
    ReservationNotFound,
    SKUIsRequired,
    StockAlreadyExists,
    StockNegative,
    StockNotFound,
)
from app.inventory.models.enums import ReservationStatus, StockMovementType
from app.inventory.models.reservation import StockReservation
from app.inventory.models.stock import InventoryStock, StockMovement
from app.inventory.repositories.category_repo import CategoryRepository
from app.inventory.repositories.location_repo import LocationRepository
from app.inventory.repositories.product_repo import ProductRepository
from app.inventory.repositories.reservation_repo import ReservationRepository
from app.inventory.repositories.stock_repo import StockRepository

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(
        self,
        stock_repo: StockRepository,
        product_repo: ProductRepository,
        category_repo: CategoryRepository,
        location_repo: LocationRepository,
        reservation_repo: ReservationRepository,
    ):
        self.stock_repo = stock_repo
        self.product_repo = product_repo
        self.category_repo = category_repo
        self.location_repo = location_repo
        self.reservation_repo = reservation_repo

    # product

    async def get_product(self, product_id: uuid.UUID):
        result = await self.product_repo.get_product(product_id)
        if result is None:
            logger.warning("get_product: product not found", extra={"product_id":product_id})
            raise ProductNotFound()
        return result

    async def list_products(self):
        result = await self.product_repo.list_products()
        return result

    async def create_product(self, name: str, sku: str, category_id: uuid.UUID):
        if not name or not name.strip():
            logger.warning("create_product: called with empty name")
            raise ProductNameIsRequired()

        if not sku or not sku.strip():
            logger.warning("create_product: called with empty SKU")
            raise SKUIsRequired()

        # normalize
        name = name.strip()
        sku = sku.strip().upper()

        existing = await self.product_repo.get_by_sku(sku)
        if existing:
            logger.warning("create_product: SKU already exists", extra={"sku": sku})
            raise ProductAlreadyExits()

        category_exists = await self.category_repo.get_category(category_id)
        if not category_exists:
            logger.warning("create_product: category not found", extra={"category_id": category_id})
            raise CategoryNotFound()

        product = await self.product_repo.create_product(name, sku, category_id)
        logger.info("create_product: product created", extra={"product_id": product.id, "sku": sku})
        return product

    async def update_product(
        self,
        product_id: uuid.UUID,
        name: str | None = None,
        sku: str | None = None,
    ):
        if name is None and sku is None:
            logger.warning("update_product: called with no parameters")
            raise NoParametersProvide()

        if name is not None:
            name = name.strip()
            if not name:
                raise ProductNameIsRequired()

        if sku is not None:
            sku = sku.strip().upper()
            if not sku:
                raise SKUIsRequired()
            existing = await self.product_repo.get_by_sku(sku)
            if existing and existing.id != product_id:
                logger.warning("update_product: SKU already taken", extra={"sku": sku, "product_id": existing.id})
                raise ProductAlreadyExits()

        product = await self.product_repo.update_product(product_id, name, sku)
        if not product:
            logger.warning("update_product: product not found", extra={"product_id": product_id})
            raise ProductNotFound()

        logger.info("update_product: product updated", extra={"product_id": product_id})
        return product

    async def activate_product(self, product_id: uuid.UUID):
        product = await self.product_repo.activate_product(product_id)
        if not product:
            logger.warning("activate_product: product not found", extra={"product_id": product_id})
            raise ProductNotFound()

        logger.info("activate_product: product activated", extra={"product_id": product_id})
        return product

    async def deactivate_product(self, product_id: uuid.UUID):
        product = await self.product_repo.deactivate_product(product_id)
        if not product:
            logger.warning("deactivate_product: product not found", extra={"product_id": product_id})
            raise ProductNotFound()

        logger.info("deactivate_product: product deactivated", extra={"product_id": product_id})
        return product

    # category

    async def create_category(self, name: str, description: str):
        if not name or not name.strip():
            logger.warning("create_category: called with empty name")
            raise CategoryNameIsRequired()

        if not description or not description.strip():
            logger.warning("create_category: called with empty description")
            raise CategoryDescriptionIsRequired()

        name = name.strip()
        description = description.strip()

        existing = await self.category_repo.get_by_name(name)
        if existing:
            logger.warning("create_category: name already exists", extra={"category_name": name})
            raise CategoryAlreadyExists()

        category = await self.category_repo.create_category(name, description)
        logger.info("create_category: category created", extra={"category_id": category.id, "category_name": name})
        return category

    async def delete_category(self, category_id: uuid.UUID):
        deleted = await self.category_repo.delete_category(category_id)
        if not deleted:
            logger.warning("delete_category: category not found", extra={"category_id": category_id})
            raise CategoryNotFound()
        logger.info("delete_category: category deleted", extra={"category_id": category_id})

    async def add_product_to_category(self, product_id: uuid.UUID, category_id: uuid.UUID):
        category = await self.category_repo.get_category(category_id)
        if not category:
            logger.warning("add_product_to_category: category not found", extra={"category_id": category_id})
            raise CategoryNotFound()
        
        product = await self.product_repo.get_product(product_id)

        if product not in category.products:
            category.products.append(product)
            await self.category_repo.save_category(category)

        logger.info("product saved in category", extra={"category_id": category_id, "product_id": product_id})
        return category

    async def remove_product_from_category(self, product_id: uuid.UUID, category_id: uuid.UUID):
        category = await self.category_repo.get_category(category_id)
        if not category:
            logger.warning("remove_product_from_category: category not found", extra={"category_id": category_id})
            raise CategoryNotFound()

        product = await self.product_repo.get_product(product_id)

        logger.info("product removed from category", extra={"category_id": category_id, "product_id": product_id})
        return await self.category_repo.remove_product(category, product)

    # stock

    async def initialize_stock(
        self, location_id: uuid.UUID, product_id: uuid.UUID, quantity: int, reorder_point: int
    ):
        quantity = abs(int(quantity))
        reorder_point = abs(int(reorder_point))

        # ensure reorder_point doesn't exceed quantity
        reorder_point = min(reorder_point, quantity)

        location = await self.location_repo.get_location(location_id)
        if not location:
            logger.warning("initialize_stock: invalid or empty location", extra={"location_id": location_id})
            raise InvalidLocation()

        await self.product_repo.get_product(product_id)

        if quantity <= 0:
            logger.warning("initialize_stock: 0 or negative quantity", extra={"quantity": quantity})
            raise InvalidQuantityStock()

        existing = await self.stock_repo.get_stock_by_location_and_product_for_update(
            product_id=product_id, location_id=location_id
        )
        if existing:
            logger.warning(
                "initialize_stock: stock already exists for product/location",
                extra={"product_id": product_id, "location_id": location_id, "stock_id": existing.id},
            )
            raise StockAlreadyExists()

        stock_creation = await self.stock_repo.initialize_stock(
            location_id, product_id, quantity, reorder_point
        )

        logger.info(
            "initialize_stock: stock created",
            extra={"stock_id": stock_creation.id, "product_id": product_id, "location_id": location_id, "quantity": quantity},
        )
        return stock_creation

    async def add_stock(self, product_id, location_id, quantity, user_id):
        if quantity <= 0:
            logger.warning("add_stock: 0 or negative quantity", extra={"quantity": quantity})
            raise InvalidQuantityStock()

        stock = await self.stock_repo.get_stock_by_location_and_product_for_update(
            product_id, location_id
        )
        if not stock:
            logger.warning("add_stock: invalid product or location", extra={"product_id": product_id, "location_id": location_id})
            raise InvalidProductOrLocation()

        previous_quantity = stock.quantity

        stock.quantity += quantity
        new_quantity = stock.quantity

        movement = StockMovement(
            stock_id=stock.id,
            movement_type=StockMovementType.IN,
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            created_by=user_id,
        )
        await self.stock_repo.update_quantity_stock(stock)
        await self.stock_repo.create_movement(movement)

        logger.info(
            "add_stock: movement created",
            extra={"stock_id": stock.id, "quantity": quantity, "new_quantity": new_quantity, "user_id": user_id},
        )
        return movement

    async def remove_stock(self, product_id, location_id, quantity, user_id):
        if quantity <= 0:
            logger.warning("remove_stock: 0 or negative quantity", extra={"quantity": quantity})
            raise InvalidQuantityStock()

        stock = await self.stock_repo.get_stock_by_location_and_product_for_update(
            product_id, location_id
        )
        if not stock:
            logger.warning("remove_stock: invalid product or location", extra={"product_id": product_id, "location_id": location_id})
            raise InvalidProductOrLocation()

        if stock.quantity < quantity:
            logger.warning("remove_stock: quantity exceeds available stock", extra={"stock_id": stock.id, "quantity": quantity, "available": stock.quantity})
            raise StockNegative()

        previous_quantity = stock.quantity

        stock.quantity -= quantity
        new_quantity = stock.quantity

        movement = StockMovement(
            stock_id=stock.id,
            movement_type=StockMovementType.OUT,
            quantity=quantity,
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            created_by=user_id,
        )
        await self.stock_repo.update_quantity_stock(stock)
        await self.stock_repo.create_movement(movement)

        logger.info(
            "remove_stock: movement created",
            extra={"stock_id": stock.id, "quantity": quantity, "new_quantity": new_quantity, "user_id": user_id},
        )
        return movement

    async def adjust_stock(self, product_id, location_id, quantity, user_id):
        stock = await self.stock_repo.get_stock_by_location_and_product_for_update(
            product_id, location_id
        )
        if not stock:
            logger.warning("adjust_stock: invalid product or location", extra={"product_id": product_id, "location_id": location_id})
            raise InvalidProductOrLocation()

        if quantity < 0:
            logger.warning("adjust_stock: negative quantity", extra={"quantity": quantity})
            raise StockNegative()

        previous_quantity = stock.quantity
        stock.quantity = quantity
        new_quantity = stock.quantity

        movement = StockMovement(
            stock_id=stock.id,
            movement_type=StockMovementType.ADJUST,
            quantity=abs(new_quantity - previous_quantity),  # store the difference
            previous_quantity=previous_quantity,
            new_quantity=new_quantity,
            created_by=user_id,
        )

        await self.stock_repo.update_quantity_stock(stock)
        await self.stock_repo.create_movement(movement)

        logger.info(
            "adjust_stock: movement created",
            extra={"stock_id": stock.id, "previous_quantity": previous_quantity, "new_quantity": new_quantity, "user_id": user_id},
        )
        return movement

    async def list_stock_movements(self, stock_id: uuid.UUID, location_id: uuid.UUID, limit: int = 100):
        stock = await self.stock_repo.get_stock(stock_id)
        if not stock:
            logger.warning("list_stock_movements: stock not found", extra={"stock_id": stock_id})
            raise StockNotFound()

        # guard: a branch may only read movement history for its own stock
        if stock.location_id != location_id:
            logger.warning(
                "list_stock_movements: stock belongs to another location",
                extra={"stock_id": stock_id, "stock_location_id": stock.location_id, "current_location_id": location_id},
            )
            raise StockNotFound()

        return await self.stock_repo.list_stock_movements(stock_id, limit)

    async def get_stock_levels(
        self,
        location_id: Optional[uuid.UUID] = None,
        product_id: Optional[uuid.UUID] = None,
    ) -> list[InventoryStock]:

        return await self.stock_repo.get_stock_levels(
            location_id=location_id, product_id=product_id
        )

    # location

    async def get_location_list(self):
        result = await self.location_repo.list_locations()
        return result

    async def get_location(self, location_id: uuid.UUID):
        location = await self.location_repo.get_location(location_id)
        if location is None:
            logger.warning("get_location: location not found", extra={"location_id": location_id})
            raise LocationNotFound()
        return location

    async def create_location(self, name: str, city: str, address: str):
        if not name or not name.strip():
            logger.warning("create_location: called with empty name")
            raise LocationNameIsRequired()

        if not city or not city.strip():
            logger.warning("create_location: called with empty city")
            raise LocationCityIsRequired()

        if not address or not address.strip():
            logger.warning("create_location: called with empty address")
            raise LocationAddressIsRequired()

        name = name.strip()
        city = city.strip()
        address = address.strip()

        existing = await self.location_repo.get_by_name(name)
        if existing:
            logger.warning("create_location: name already exists", extra={"location_name": name})
            raise LocationAlreadyExists()

        location = await self.location_repo.create_location(name, city, address)
        logger.info("create_location: location created", extra={"location_id": location.id, "location_name": name})
        return location

    async def update_location(
        self,
        location_id: uuid.UUID,
        name: str | None = None,
        city: str | None = None,
        address: str | None = None,
    ):
        if name is None and city is None and address is None:
            logger.warning("update_location: called with no parameters")
            raise NoParametersProvide()

        if name is not None:
            name = name.strip()
            if not name:
                raise LocationNameIsRequired()
            existing = await self.location_repo.get_by_name(name)
            if existing and existing.id != location_id:
                logger.warning("update_location: name already taken", extra={"location_name": name, "location_id": existing.id})
                raise LocationAlreadyExists()

        if city is not None:
            city = city.strip()
            if not city:
                raise LocationCityIsRequired()

        if address is not None:
            address = address.strip()
            if not address:
                raise LocationAddressIsRequired()

        location = await self.location_repo.update_location(location_id, name, city, address)
        if not location:
            logger.warning("update_location: location not found", extra={"location_id": location_id})
            raise LocationNotFound()

        logger.info("update_location: location updated", extra={"location_id": location_id})
        return location

    async def delete_location(self, location_id: uuid.UUID):
        location = await self.location_repo.get_location(location_id)
        if not location:
            logger.warning("delete_location: location not found", extra={"location_id": location_id})
            raise LocationNotFound()

        if await self.stock_repo.location_has_stock(location_id):
            logger.warning("delete_location: location still has stock", extra={"location_id": location_id})
            raise LocationHasStock()

        await self.location_repo.delete_location(location_id)
        logger.info("delete_location: location deleted", extra={"location_id": location_id})

    # reservation

    async def reserve_for_item(
        self,
        order_item_id: uuid.UUID,
        product_id: uuid.UUID,
        location_id: uuid.UUID,
        quantity: int,
    ) -> StockReservation:
        if quantity <= 0:
            logger.warning("reserve_for_item: 0 or negative quantity", extra={"quantity": quantity})
            raise InvalidQuantityStock()

        stock = await self.stock_repo.get_stock_by_location_and_product_for_update(
            product_id=product_id,
            location_id=location_id,
        )
        if not stock:
            logger.warning("reserve_for_item: stock not found", extra={"product_id": product_id, "location_id": location_id})
            raise StockNotFound()

        available = stock.quantity - stock.reserved_quantity
        if available < quantity:
            logger.warning(
                "reserve_for_item: insufficient stock",
                extra={"product_id": product_id, "available": available, "requested": quantity},
            )
            raise InsufficientStock()

        stock.reserved_quantity += quantity
        reservation = await self.reservation_repo.create_reservation(
            order_item_id=order_item_id,
            stock_id=stock.id,
            quantity=quantity,
        )
        logger.info(
            "reserve_for_item: reservation created",
            extra={"reservation_id": reservation.id, "stock_id": stock.id, "quantity": quantity},
        )
        return reservation

    async def release_for_item(self, reservation_id: uuid.UUID) -> StockReservation:
        reservation = await self.stock_repo.get_reservation_by_id_for_update(reservation_id)
        if not reservation:
            logger.warning("release_for_item: reservation not found", extra={"reservation_id": reservation_id})
            raise ReservationNotFound()

        if reservation.status != ReservationStatus.RESERVED:
            logger.warning("release_for_item: invalid reservation status", extra={"reservation_id": reservation_id, "status": reservation.status})
            raise InvalidReservationStatus()

        stock = await self.stock_repo.get_stock_by_id_for_update(
            reservation.stock_id
        )
        if not stock:
            logger.warning("release_for_item: stock not found", extra={"reservation_id": reservation.id, "stock_id": reservation.stock_id})
            raise StockNotFound()

        stock.reserved_quantity -= reservation.quantity
        reservation.status = ReservationStatus.RELEASED

        logger.info("release_for_item: reservation released", extra={"reservation_id": reservation.id, "stock_id": stock.id})
        return reservation

    async def fulfill_for_item(self, reservation_id: uuid.UUID) -> StockReservation:
        reservation = await self.stock_repo.get_reservation_by_id_for_update(reservation_id)
        if not reservation:
            logger.warning("fulfill_for_item: reservation not found", extra={"reservation_id": reservation_id})
            raise ReservationNotFound()

        if reservation.status != ReservationStatus.RESERVED:
            logger.warning("fulfill_for_item: invalid reservation status", extra={"reservation_id": reservation_id, "status": reservation.status})
            raise InvalidReservationStatus()

        stock = await self.stock_repo.get_stock_by_id_for_update(
            reservation.stock_id
        )
        if not stock:
            logger.warning("fulfill_for_item: stock not found", extra={"reservation_id": reservation.id, "stock_id": reservation.stock_id})
            raise StockNotFound()

        stock.quantity -= reservation.quantity
        stock.reserved_quantity -= reservation.quantity
        reservation.status = ReservationStatus.FULFILLED

        logger.info("fulfill_for_item: reservation fulfilled", extra={"reservation_id": reservation.id, "stock_id": stock.id})
        return reservation
