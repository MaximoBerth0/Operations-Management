# Inventory Module

Source: [app/inventory/](../../app/inventory/)

## Purpose

Manages products, categories, physical locations, and per-location stock — with a full audit trail of every quantity change. Stock movements are **append-only**: every adjustment to `quantity` produces an immutable `StockMovement` row alongside the updated `InventoryStock` row.

## Architecture

```
┌──────────┐  M:N   ┌────────────┐
│ Products │◀──────▶│ Categories │
└────┬─────┘        └────────────┘
     │ 1:N
     ▼
┌──────────────────┐  1:N (audit) ┌──────────────────┐
│ InventoryStock   │─────────────▶│  StockMovement   │
│ (product+location│              │ (IN/OUT/ADJUST)  │
│  qty + reserved) │              └──────────────────┘
└────────┬─────────┘
         │ 1:N   ┌────────────────────────┐  1:1  ┌──────────────┐
         ├──────▶│   StockReservation     │──────▶│  OrderItem   │
         │       │ (RESERVED/FULFILLED/…) │       │ (orders mod) │
         │ N:1   └────────────────────────┘       └──────────────┘
         ▼
   ┌────────────┐
   │  Location  │
   └────────────┘
```

`InventoryStock` is the only mutable quantity. It has two axes:

- **`quantity`** — on-hand. Every change is paired with a `StockMovement` capturing `previous_quantity`, `new_quantity`, `movement_type`, and `created_by`.
- **`reserved_quantity`** — held by open reservations, driven by the [orders](orders.md) module. Available-to-promise = `quantity − reserved_quantity`.

Products soft-delete (`is_active` flag, not a hard delete). Locations have full CRUD but cannot be deleted while they still hold stock.

## Flow

**Stock mutation** (`in` / `out` / `adjust`) — look up the stock row by the (location, product) key → validate (`out` can't go below 0; `adjust` target ≥ 0) → write the new `quantity` **and** an audit `StockMovement` (`created_by = current user`), through the same session.

**Reservations** (called by the orders module inside *its* transaction) all take a `SELECT … FOR UPDATE` row lock so overlapping confirmations against the same stock row serialize instead of overselling:

- **reserve** — checks `quantity − reserved_quantity ≥ requested` (else `InsufficientStock`), bumps `reserved_quantity`, creates a `RESERVED` reservation.
- **release** — decrements `reserved_quantity`, status → `RELEASED`. On-hand `quantity` untouched.
- **fulfill** — decrements **both** `quantity` and `reserved_quantity`, status → `FULFILLED`. This is the real outflow.

## Endpoints

All under the `/inventory` prefix; every route requires a permission. Stock-mutating routes also require auth so `current_user.id` is recorded on the movement.

**Products**

| Endpoint | Permission |
|---|---|
| `GET /inventory/products` · `GET /inventory/products/{id}` | `product:view` |
| `POST /inventory/products` | `product:create` |
| `PATCH /inventory/products/{id}` | `product:update` |
| `DELETE /inventory/products/{id}` | `product:deactivate` (soft delete) |
| `POST /inventory/products/{id}/activate` | `product:activate` |

**Categories**

| Endpoint | Permission |
|---|---|
| `POST /inventory/categories` | `category:create` |
| `DELETE /inventory/categories/{id}` | `category:delete` |
| `POST /inventory/categories/{category_id}/products` | `category:create` |
| `DELETE /inventory/categories/{category_id}/products` | `category:remove` |

**Stock**

| Endpoint | Permission |
|---|---|
| `POST /inventory/new` | `stock:create` (initialize a stock row) |
| `POST /inventory/in` · `out` · `adjust` | `stock:in` / `stock:out` / `stock:adjust` |
| `GET /inventory/movements?stock_id&limit` | `stock:view` |
| `GET /inventory/stock?location_id&product_id` | `stock:view` |

**Locations**

| Endpoint | Permission |
|---|---|
| `GET /inventory/locations` | `location:list` |
| `GET /inventory/locations/{id}` | `location:view` |
| `POST /inventory/locations` | `location:create` |
| `PATCH /inventory/locations/{id}` | `location:update` |
| `DELETE /inventory/locations/{id}` | `location:delete` (409 if it still has stock) |

`location:list` / `location:view` are granted to admin and employee; create/update/delete are admin-only.

## Error cases

Extend `InventoryError` (base 400 / `INVENTORY_ERROR`). See [app/inventory/exceptions.py](../../app/inventory/exceptions.py).

| Exception | HTTP | Code |
|---|---|---|
| `ProductNotFound` | 404 | `PRODUCT_NOT_FOUND` |
| `ProductAlreadyExits` | 409 | `PRODUCT_ALREADY_EXISTS` |
| `ProductNameIsRequired` / `SKUIsRequired` | 400 | `PRODUCT_NAME_IS_REQUIRED` / `SKU_IS_REQUIRED` |
| `CategoryNotFound` | 404 | `CATEGORY_NOT_FOUND` |
| `CategoryAlreadyExists` | 409 | `CATEGORY_ALREADY_EXISTS` |
| `CategoryNameIsRequired` / `CategoryDescriptionIsRequired` | 400 | `CATEGORY_*_IS_REQUIRED` |
| `LocationNotFound` | 404 | `LOCATION_NOT_FOUND` |
| `LocationAlreadyExists` | 409 | `LOCATION_ALREADY_EXISTS` |
| `LocationHasStock` | 409 | `LOCATION_HAS_STOCK` |
| `LocationNameIsRequired` / `LocationCityIsRequired` / `LocationAddressIsRequired` | 400 | `LOCATION_*_IS_REQUIRED` |
| `InvalidLocation` | 400 | `INVALID_LOCATION_ID` |
| `StockNotFound` | 404 | `STOCK_NOT_FOUND` |
| `StockAlreadyExists` | 409 | `STOCK_ALREADY_EXISTS` |
| `StockNegative` | 400 | `STOCK_NEGATIVE` |
| `InsufficientStock` | 409 | `INSUFFICIENT_STOCK` |
| `InvalidQuantityStock` | 400 | `INVALID_QUANTITY_STOCK` |
| `InvalidProductOrLocation` | 400 | `INVALID_PRODUCT_OR_LOCATION` |
| `NoParametersProvide` | 400 | `NO_PARAMETERS_PROVIDE` |
| `ReservationNotFound` | 404 | `RESERVATION_NOT_FOUND` |
| `InvalidReservationStatus` | 409 | `INVALID_RESERVATION_STATUS` |
