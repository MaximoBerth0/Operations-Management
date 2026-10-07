import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.inventory.models.enums import StockMovementType


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# request


class ProductCreate(ORMModel):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=100)
    category_id: uuid.UUID


class ProductUpdate(ORMModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    sku: str | None = Field(None, min_length=1, max_length=100)


class CategoryCreate(ORMModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=255)


class AddProductToCategory(ORMModel):
    product_id: uuid.UUID


class RemoveProducFromCategory(ORMModel):
    product_id: uuid.UUID


class LocationCreate(ORMModel):
    name: str = Field(..., min_length=1, max_length=255)
    city: str = Field(..., min_length=1, max_length=255)
    address: str = Field(..., min_length=1, max_length=255)


class LocationUpdate(ORMModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    city: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, min_length=1, max_length=255)


class StockInitialize(ORMModel):
    product_id: uuid.UUID = Field()
    quantity: int = Field()
    reorder_point: int = Field()


class StockTransaction(ORMModel):
    product_id: uuid.UUID = Field()
    quantity: int = Field()
    reason: Optional[str] = Field(None, max_length=500)


# response


class ProductListItemResponse(ORMModel):
    id: uuid.UUID
    name: str
    sku: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProductResponse(ORMModel):
    id: uuid.UUID
    name: str
    sku: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CategoryResponse(ORMModel):
    id: uuid.UUID
    name: str
    description: str


class StockMovementResponse(ORMModel):
    id: uuid.UUID
    stock_id: uuid.UUID
    movement_type: StockMovementType
    quantity: int
    previous_quantity: int
    new_quantity: int
    created_by: uuid.UUID
    created_at: datetime


class StockResponse(ORMModel):
    id: uuid.UUID
    location_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int
    reserved_quantity: int
    reorder_point: int
    created_at: datetime
    updated_at: datetime


class StockMovementListResponse(ORMModel):
    items: List[StockMovementResponse]
    total: int


class LocationResponse(ORMModel):
    id: uuid.UUID
    name: str
    city: str
    address: str


class LocationListResponse(ORMModel):
    items: List[LocationResponse]
    total: int


class StockListResponse(ORMModel):
    items: List[StockResponse]
    total: int


class ReplenishmentItemResponse(ORMModel):
    stock_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    location_id: uuid.UUID
    location_name: str
    quantity: int
    reserved_quantity: int
    reorder_point: int
    available: int
    daily_consumption: float
    days_of_coverage: float | None
    needs_restock: bool
    suggested_quantity: int


class ReplenishmentListResponse(ORMModel):
    items: List[ReplenishmentItemResponse]
    total: int
