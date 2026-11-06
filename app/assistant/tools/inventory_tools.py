"""Thin adapters over InventoryService. No logic here: if a tool starts
computing, that code belongs in the service."""
import uuid

from pydantic import BaseModel, Field

from app.assistant.tools.base import Tool, ToolContext
from app.inventory.models.stock import InventoryStock
from app.inventory.schemas import (
    LocationListResponse,
    ProductResponse,
    ReplenishmentItemResponse,
    ReplenishmentListResponse,
    StockMovementResponse,
)

LOCATION_HINT = "Location id, any location is allowed. Omit to use the user's current location."
LIMIT_HINT = "Max rows returned. total still counts every row."


class StockRow(BaseModel):
    """A stock row as the model sees it: always tied to a named product and location."""

    stock_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    location_id: uuid.UUID
    location_name: str
    quantity: int
    reserved_quantity: int
    reorder_point: int


def _stock_row(stock: InventoryStock) -> StockRow:
    return StockRow(
        stock_id=stock.id,
        product_id=stock.product_id,
        product_name=stock.product.name,
        sku=stock.product.sku,
        location_id=stock.location_id,
        location_name=stock.location.name,
        quantity=stock.quantity,
        reserved_quantity=stock.reserved_quantity,
        reorder_point=stock.reorder_point,
    )


# get_replenishment_suggestions

class ReplenishmentArgs(BaseModel):
    location_id: uuid.UUID | None = Field(None, description=LOCATION_HINT)
    horizon_days: int | None = Field(
        None, ge=1, le=30, description="Restock if stock runs out within this many days. Default 7."
    )
    limit: int = Field(50, ge=1, le=200, description=LIMIT_HINT)


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
        for r in rows[: args.limit]
    ]
    return ReplenishmentListResponse(items=items, total=len(rows))


GET_REPLENISHMENT = Tool(
    name="get_replenishment_suggestions",
    description=(
        "Products that should be restocked at a location, most urgent first, "
        "with daily consumption, days of coverage and suggested quantity. "
        "If total is above the items returned, the list was cut by limit."
    ),
    input_schema=ReplenishmentArgs,
    permission="stock:view",
    handler=get_replenishment,
)


# get_stock_levels

class StockLevelsArgs(BaseModel):
    location_id: uuid.UUID | None = Field(None, description=LOCATION_HINT)
    product_id: uuid.UUID | None = Field(None, description="Only this product.")
    limit: int = Field(50, ge=1, le=200, description=LIMIT_HINT)


class StockLevelList(BaseModel):
    items: list[StockRow]
    total: int


async def get_stock_levels(args: StockLevelsArgs, ctx: ToolContext) -> StockLevelList:
    stocks = await ctx.inventory_service.get_stock_levels(
        location_id=args.location_id or ctx.location_id, product_id=args.product_id
    )
    return StockLevelList(items=[_stock_row(s) for s in stocks[: args.limit]], total=len(stocks))


GET_STOCK_LEVELS = Tool(
    name="get_stock_levels",
    description=(
        "Current quantity, reserved quantity and reorder point of each product at a location, "
        "with product and location names. "
        "If total is above the items returned, the list was cut by limit: filter by product_id."
    ),
    input_schema=StockLevelsArgs,
    permission="stock:view",
    handler=get_stock_levels,
)


# list_stock_movements

class StockMovementsArgs(BaseModel):
    stock_id: uuid.UUID = Field(
        ..., description="Stock row id from get_stock_levels. Any location is allowed."
    )
    limit: int = Field(20, ge=1, le=100)


class StockHistoryResult(BaseModel):
    stock: StockRow
    items: list[StockMovementResponse]
    total: int


async def list_stock_movements(args: StockMovementsArgs, ctx: ToolContext) -> StockHistoryResult:
    history = await ctx.inventory_service.get_stock_history(args.stock_id, limit=args.limit)
    return StockHistoryResult(
        stock=_stock_row(history.stock),
        items=[StockMovementResponse.model_validate(m) for m in history.movements],
        total=len(history.movements),
    )


LIST_STOCK_MOVEMENTS = Tool(
    name="list_stock_movements",
    description=(
        "Latest in/out/adjust movements of one stock row, newest first, "
        "with the product and location the row belongs to."
    ),
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


# search_products

class SearchProductsArgs(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=100, description="Part of the product name or SKU."
    )
    limit: int = Field(20, ge=1, le=100, description=LIMIT_HINT)


class ProductMatch(BaseModel):
    product_id: uuid.UUID
    name: str
    sku: str
    is_active: bool


class ProductSearchResult(BaseModel):
    items: list[ProductMatch]
    total: int


async def search_products(args: SearchProductsArgs, ctx: ToolContext) -> ProductSearchResult:
    products = await ctx.inventory_service.search_products(args.query)
    items = [
        ProductMatch(product_id=p.id, name=p.name, sku=p.sku, is_active=p.is_active)
        for p in products[: args.limit]
    ]
    return ProductSearchResult(items=items, total=len(products))


SEARCH_PRODUCTS = Tool(
    name="search_products",
    description=(
        "Find products by part of their name or SKU, case-insensitive. Use it to get the "
        "product_id when the employee names a product. If several match, ask which one."
    ),
    input_schema=SearchProductsArgs,
    permission="product:view",
    handler=search_products,
)


INVENTORY_TOOLS = [
    SEARCH_PRODUCTS,
    GET_REPLENISHMENT,
    GET_STOCK_LEVELS,
    LIST_STOCK_MOVEMENTS,
    LIST_LOCATIONS,
    GET_PRODUCT,
]
