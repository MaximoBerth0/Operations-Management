# Database Design

## Overview

A single **PostgreSQL** database, accessed asynchronously through SQLAlchemy 2.0 (`asyncpg` driver). Each feature module owns its tables; relationships that cross module boundaries are expressed as foreign keys with explicit cascade rules rather than shared ORM base classes. Schema changes are versioned with **Alembic** and applied automatically at container start (see [deployment](deployment.md)).

The domain, at a glance:

- **users / rbac** — `users`, `roles`, `permissions`, and the association tables `user_roles` and `role_permissions` (composite PKs, cascading deletes). Access is indirect: users → roles → permissions.
- **inventory** — `products`, `categories` (M:N), `locations`, `inventory_stock` (per location+product), and the append-only `stock_movement` audit log.
- **orders** — `orders` (state machine) → `order_items` → `stock_reservation`, the last bridging an order line to the inventory stock it holds.

The full engine and session setup lives in [app/database/session.py](../app/database/session.py); tunables are in [app/core/config.py](../app/core/config.py).

## Technical decisions

**Async everywhere.** The app uses `create_async_engine` + `async_sessionmaker` with asyncpg. FastAPI dependencies yield a session per request that **auto-commits on success and auto-rolls-back on any exception**, so handlers don't manage transaction boundaries by hand. Services that need multi-write atomicity commit once explicitly.

**`expire_on_commit=False`.** Committed ORM objects stay usable after the transaction closes, so response serialization doesn't trigger surprise lazy-load queries (which would fail on an async session). Relationships that responses need are eager-loaded (`selectinload`) in the repository instead.

**Configurable connection pooling.** All pool parameters are settings, so the same image tunes to its environment without code changes ([config.py](../app/core/config.py)):

| Setting | Default | Purpose |
|---|---|---|
| `DB_POOL_SIZE` | 20 | Persistent connections held open |
| `DB_MAX_OVERFLOW` | 10 | Extra connections allowed under burst |
| `DB_POOL_TIMEOUT` | 30s | Wait for a free connection before erroring |
| `DB_POOL_RECYCLE` | 3600s | Recycle connections hourly (avoids stale server-side closes) |
| `DB_POOL_PRE_PING` | true | Validate a connection before use (drops dead ones transparently) |
| `DB_ECHO` | false | SQL statement logging (dev only) |

**Layered timeouts.** Failures are bounded at every level so a slow or hung query can't pin a worker indefinitely — connect (`DB_CONNECT_TIMEOUT` 10s), per-command (`DB_COMMAND_TIMEOUT` 60s), and a server-side `statement_timeout` (`DB_STATEMENT_TIMEOUT` 30000ms) pushed into Postgres itself.

**TLS enforced.** Connections require SSL (`ssl: "require"` in `connect_args`) — RDS is never reached in plaintext.

**Concurrency via row locks.** Overselling is prevented at the database, not in application logic: stock reservation reads take `SELECT … FOR UPDATE` on the stock row, so two orders confirming against the same (product, location) serialize instead of both passing the availability check (see [inventory](modules/inventory.md)).

**Append-only audit.** `stock_movement` rows are never mutated — every `quantity` change writes a new movement capturing `previous_quantity`, `new_quantity`, type, and `created_by`, in the same session as the stock update.

**Migrations, not `create_all`.** Schema is owned by Alembic and applied via `alembic upgrade head` on startup. Alembic is idempotent, so multiple tasks booting at once is safe; a task can opt out with `RUN_MIGRATIONS=false`. Permission/role reference data is populated separately by the one-off seeders in `app/bootstraps/`.
