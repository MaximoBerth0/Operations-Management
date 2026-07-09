# Orders Module

Source: [app/orders/](../../app/orders/)

## Purpose

Manages the order lifecycle: create an order, add/remove line items while it is still a draft, and drive it through its state transitions. The order owns no stock logic — reserving, releasing, and fulfilling inventory is delegated to the [inventory](inventory.md) module, with the order service orchestrating both sides in one transaction.

Each order also carries a short, human-typable **lookup code** (`XXXX-XXXX`) so a customer can retrieve their order through a single **public, unauthenticated** endpoint. The code itself is the credential.

## Architecture

```
┌──────────┐  1:N   ┌──────────────┐  1:1 (opt) ┌──────────────────┐
│  Order   │───────▶│  OrderItem   │───────────▶│ StockReservation │
│ (status) │        │ (product+qty)│            │  (inventory mod) │
└──────────┘        └──────────────┘            └──────────────────┘
```

The `Order` is a small **state machine**. Item edits are allowed only while `CREATED`; once confirmed, its items are mirrored as `StockReservation`s in the inventory module.

```
        add/remove items
        ┌───────────┐
        ▼           │
   ┌─────────┐ confirm  ┌───────────┐ complete ┌───────────┐
   │ CREATED │─────────▶│ CONFIRMED │─────────▶│ COMPLETED │
   └────┬────┘          └─────┬─────┘          └───────────┘
        │ cancel              │ cancel
        ▼                     ▼
   ┌───────────┐        ┌───────────┐
   │ CANCELLED │        │ CANCELLED │
   └───────────┘        └───────────┘
```

`COMPLETED` and `CANCELLED` are terminal. The lookup `code` is drawn from a Crockford-style base32 alphabet (ambiguous `I L O U` omitted) via `secrets.choice`; it is never echoed back in responses or logs.

## Flow

Transitions that touch inventory (`confirm`, `cancel`, `complete`) are wrapped in a **service-owned transaction** — the order row and the reservation rows commit or roll back together. An exception from any inventory call propagates before the single `commit()`, leaving the order un-transitioned.

- **confirm** (requires `CREATED`) — reserves stock for every line item, then flips to `CONFIRMED`.
- **cancel** (requires `CONFIRMED`) — releases each reservation, then `CANCELLED`. Stock quantity is untouched (goods never shipped).
- **complete** (requires `CONFIRMED`) — fulfills each reservation (draws stock down), then `COMPLETED`.

**Public lookup** (`GET /orders/code/{code}`) normalizes the input (upper-case, strip whitespace, re-insert the dash) so `abcd1234`, `ABCD-1234`, and ` ABCD 1234 ` all resolve. A malformed code and a well-formed-but-unknown code both raise the same `OrderNotFound` (404), so the endpoint never reveals which codes are well-formed.

## Endpoints

All under the `/orders` prefix.

| Endpoint | Auth |
|---|---|
| `GET /orders/code/{code}` | **None — public.** The code is the credential |
| `GET /orders/me` | Authenticated only (self-scoped, no permission) |
| `POST /orders` | `order:create` (+ auth to record the owner) |
| `POST /orders/{id}/items` | `order:add` |
| `DELETE /orders/{order_id}/items/{product_id}` | `order:remove` |
| `PATCH /orders/{id}/confirm` | `order:confirm` (+ `X-Location-Id` header) |
| `PATCH /orders/{id}/cancel` | `order:cancel` |
| `PATCH /orders/{id}/complete` | `order:complete` |

The public lookup uses a `/code/` literal segment so its `str` param never collides with the UUID `/{id}` routes. It is the natural candidate for rate-limiting given its guessable keyspace (32⁸ ≈ 1.1 × 10¹²).

## Error cases

Extend `OrderError` (base 400 / `ORDER_ERROR`). See [app/orders/exceptions.py](../../app/orders/exceptions.py).

| Exception | HTTP | Code | When |
|---|---|---|---|
| `OrderNotFound` | 404 | `ORDER_NOT_FOUND` | Order id or lookup code misses |
| `InvalidOrderStatus` | 409 | `INVALID_ORDER_STATUS` | Illegal transition (e.g. confirm a non-`CREATED` order) |
| `OrderItemNotFound` | 404 | `ORDER_ITEM_NOT_FOUND` | Removing an item not on the order |
| `InvalidQuantity` | 422 | `INVALID_QUANTITY` | Item quantity ≤ 0 |
| `OrderCodeGenerationError` | 500 | `ORDER_GENERATION_CODE_FAILED` | Code retries exhausted (practically unreachable) |

Model transition guards raise these typed exceptions directly (never raw `ValueError`s), so illegal states surface as proper responses through the global `AppError` handler.
