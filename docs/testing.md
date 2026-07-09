# Testing

## Overview

The suite is **integration-first**: tests drive the real FastAPI app through an in-process HTTP client and assert against a **real PostgreSQL database** — no mocked repositories, no SQLite substitute. This exercises the full `router → service → repository → model` stack, real SQL (including Postgres-specific behavior like `FOR UPDATE` row locks and enum types), and the actual auth/RBAC dependencies on every request.

Because the tests hit a real database, **you must start a throwaway PostgreSQL container before running them**. Tests point at `localhost:5432`; nothing creates that database for you.

Tests live under [`integration/`](../integration/), grouped by module, with all wiring in [`integration/conftest.py`](../integration/conftest.py).

## You need a Docker database

The tests connect to a disposable Postgres instance defined in [`docker/docker-compose-test.yml`](../docker/docker-compose-test.yml):

- image `postgres:16`, database `test_db`, user/password `user` / `password`, published on host port **5432**.

The connection string is fixed in `conftest.py`:

```
postgresql+asyncpg://user:password@localhost:5432/test_db
```

So the container must be up **before** pytest starts, and host port 5432 must be free. This is intentional — the suite validates behavior against the same engine that runs in production, not an approximation.

## Running the tests

```bash
# 1. start the throwaway test database
docker compose -f docker/docker-compose-test.yml up -d test-db

# 2. run the integration suite
pytest integration/ -v

# 3. tear the database down when done
docker compose -f docker/docker-compose-test.yml down
```

Run a subset by path or keyword as usual, e.g. `pytest integration/inventory -v` or `pytest integration/ -k stock`.

`pytest.ini` sets `asyncio_mode = auto` (async tests need no `@pytest.mark.asyncio`) and `pythonpath = .` so `app` and `integration` import cleanly.

## How the harness works

`conftest.py` sets all required settings as environment variables (`ENV=test`, a test `DATABASE_URL`, a ≥32-char `SECRET_KEY`, etc.) **before importing the app**, then clears the settings cache so those values take effect. Key fixtures:

| Fixture | Purpose |
|---|---|
| `db_session` | One connection per test. Creates the schema from `Base.metadata`, opens an outer transaction, and **rolls it back after the test** so nothing leaks between tests; drops the schema at the end. |
| `client` | An `httpx.AsyncClient` bound to the app via `ASGITransport`, with `get_session` overridden to reuse the test's `db_session` (so the request and the test share one transaction). |
| `seeded` | Inserts every permission and role from the `app/core/constants/` matrices into the test DB — the same seed the app applies at startup. |
| `admin_user` / `employee_user` / `client_user` / `plain_user` | Users pre-assigned each seeded role (plus a role-less user to distinguish 401 from 403). |
| `auth_headers` | Builds the `Authorization: Bearer …` header for a user; optionally attaches the `X-Location-Id` header the stock routes require. |
| `make_category` / `make_product` / `make_location` / `make_stock` / `make_order` / `make_order_item` | Entity builders that create test data through the real API endpoints, so setup exercises the same paths as the assertions. |

**Isolation model:** each test gets a fresh schema and every write is rolled back at teardown, so tests are independent and order-agnostic.

**Note on connection pooling:** the test engine uses `NullPool`. pytest-asyncio runs each test on a fresh event loop, but pooled asyncpg connections are bound to the loop that created them — reusing one on a later loop raises "attached to a different loop". Disabling pooling opens a new connection per test and sidesteps this.

## Test layout

```
integration/
├── conftest.py          # env setup, engine, fixtures, entity builders
├── auth/                # login, refresh, logout, password reset/change
├── user/                # registration, profile, enable/disable
├── rbac/                # roles, permissions, user-role assignment
├── inventory/           # products, categories, locations, stock movements
└── order/               # order lifecycle + stock reservations
```

Each file targets one module's endpoints end-to-end — happy paths plus the error and permission cases documented in that module's page under [`docs/modules/`](modules/).
