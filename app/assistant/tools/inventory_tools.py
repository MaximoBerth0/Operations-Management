"""Thin adapters over InventoryService. No logic here: if a tool starts
computing, that code belongs in the service."""
import uuid

from pydantic import BaseModel, Field

from app.assistant.tools.base import Tool, ToolContext
from app.inventory.schemas import (
    LocationListResponse,
    ProductResponse,
    ReplenishmentItemResponse,
    ReplenishmentListResponse,
    StockListResponse,
    StockMovementListResponse,
)

LOCATION_HINT = "Location id. Omit to use the user's current location."


# get_replenishment_suggestions

class ReplenishmentArgs(BaseModel):
    location_id: uuid.UUID | None = Field(None, description=LOCATION_HINT)
    horizon_days: int | None = Field(
        None, ge=1, le=30, description="Restock if stock runs out within this many days. Default 7."
    )


async def get_replenishment(args: ReplenishmentArgs, ctx: ToolContext) -> ReplenishmentListResponse:
    rows = await ctx.inventory_service.get_replenishment_suggestions(
        location_id=args.location_id or ctx.location_id, horizon_days=args.horizon_days
    )
    items = [
        ReplenishmentItemResponse(
            stock_id=r.stock.id,
            product_id=r.stock.product_id,
            product_name=r.stock.product.name,
            sku=r.stock.product.sku,
            location_id=r.stock.location_id,
            location_name=r.stock.location.name,
            quantity=r.stock.quantity,
            reserved_quantity=r.stock.reserved_quantity,
            reorder_point=r.stock.reorder_point,
            available=r.suggestion.available,
            daily_consumption=r.suggestion.daily_consumption,
            days_of_coverage=r.suggestion.days_of_coverage,
            needs_restock=r.suggestion.needs_restock,
            suggested_quantity=r.suggestion.suggested_quantity,
        )
        for r in rows
    ]
    return ReplenishmentListResponse(items=items, total=len(items))


GET_REPLENISHMENT = Tool(
    name="get_replenishment_suggestions",
    description=(
        "Products that should be restocked at a location, most urgent first, "
        "with daily consumption, days of coverage and suggested quantity."
    ),
    input_schema=ReplenishmentArgs,
    permission="stock:view",
    handler=get_replenishment,
)


# get_stock_levels

class StockLevelsArgs(BaseModel):
    location_id: uuid.UUID | None = Field(None, description=LOCATION_HINT)
    product_id: uuid.UUID | None = Field(None, description="Only this product.")


async def get_stock_levels(args: StockLevelsArgs, ctx: ToolContext) -> StockListResponse:
    stocks = await ctx.inventory_service.get_stock_levels(
        location_id=args.location_id or ctx.location_id, product_id=args.product_id
    )
    return StockListResponse(items=stocks, total=len(stocks))


GET_STOCK_LEVELS = Tool(
    name="get_stock_levels",
    description="Current quantity, reserved quantity and reorder point of each product at a location.",
    input_schema=StockLevelsArgs,
    permission="stock:view",
    handler=get_stock_levels,
)


# list_stock_movements

class StockMovementsArgs(BaseModel):
    stock_id: uuid.UUID = Field(..., description="Stock row id, as returned by get_stock_levels.")
    location_id: uuid.UUID | None = Field(None, description=LOCATION_HINT)
    limit: int = Field(20, ge=1, le=100)


async def list_stock_movements(args: StockMovementsArgs, ctx: ToolContext) -> StockMovementListResponse:
    movements = await ctx.inventory_service.list_stock_movements(
        stock_id=args.stock_id, location_id=args.location_id or ctx.location_id, limit=args.limit
    )
    return StockMovementListResponse(items=movements, total=len(movements))


LIST_STOCK_MOVEMENTS = Tool(
    name="list_stock_movements",
    description="Latest in/out/adjust movements of one stock row, newest first.",
    input_schema=StockMovementsArgs,
    permission="stock:view",
    handler=list_stock_movements,
)


# list_locations

class NoArgs(BaseModel):
    pass


async def list_locations(args: NoArgs, ctx: ToolContext) -> LocationListResponse:
    locations = await ctx.inventory_service.get_location_list()
    return LocationListResponse(items=locations, total=len(locations))


LIST_LOCATIONS = Tool(
    name="list_locations",
    description="All locations (branches) with their id, name, city and address.",
    input_schema=NoArgs,
    permission="location:list",
    handler=list_locations,
)


# get_product

class ProductArgs(BaseModel):
    product_id: uuid.UUID


async def get_product(args: ProductArgs, ctx: ToolContext) -> ProductResponse:
    product = await ctx.inventory_service.get_product(args.product_id)
    return ProductResponse.model_validate(product)


GET_PRODUCT = Tool(
    name="get_product",
    description="Name, SKU and active state of one product.",
    input_schema=ProductArgs,
    permission="product:view",
    handler=get_product,
)


INVENTORY_TOOLS = [
    GET_REPLENISHMENT,
    GET_STOCK_LEVELS,
    LIST_STOCK_MOVEMENTS,
    LIST_LOCATIONS,
    GET_PRODUCT,
]
