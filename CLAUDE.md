# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Management is a back-office inventory and orders API (FastAPI, async). Products sit in stock rows per location, orders reserve that stock on confirm and consume it on complete, and a low-stock email goes out when available stock drops to the reorder point. Access is role-based (`admin`, `employee`, `client`), and an LLM assistant answers employee questions over read-only inventory tools.

Deeper docs live under `docs/` (start at `docs/system_map.md`, then `docs/architecture.md` and `docs/modules/`); the assistant's design is `app/assistant/design.md`. Do not edit anything under `docs/` or `README.md` unless explicitly asked.

## Tech stack

FastAPI, SQLAlchemy 2.0 (async, asyncpg), PostgreSQL, Alembic, Pydantic v2 + pydantic-settings, PyJWT, Argon2-CFFI, Redis, Procrastinate (Postgres-backed job queue), Anthropic SDK, Sentry, AWS (ECS Fargate, RDS, Secrets Manager, SES), pytest, Poetry.

## Commands

```bash
# install
poetry install

# full stack in Docker (API + Postgres, migrations run on container start)
docker compose -f docker/docker-compose.yml up --build
docker compose -f docker/docker-compose.yml exec api python -m app.bootstraps.seed_all   # roles + permissions

# local dev against the compose db (Makefile injects the localhost DATABASE_URL)
make db-up
make migrate
poetry run uvicorn app.main:app --reload

# worker (separate process, Procrastinate)
make worker-schema   # once, job tables
make worker

# lint
poetry run ruff check .
poetry run ruff format .

# tests (test Postgres on 5433, Redis on 6379 for the rate limit tests)
docker compose -f docker/docker-compose-test.yml up -d
poetry run pytest tests/inventory -v
poetry run pytest -k test_confirm      # one test by name
docker compose -f docker/docker-compose-test.yml down

# new migration after changing models
make revision m="describe your change"
```

Required settings with no default: `DATABASE_URL`, `SECRET_KEY`, `AWS_REGION`, `SENDER_EMAIL`, `APP_BASE_URL`, `CORS_ALLOW_ORIGINS`. See `env.example` / `app/infra/config.py`. Precedence is env vars, then AWS Secrets Manager (when `AWS_SECRETS_NAME` is set), then `.env`. `ENV` defaults to `prod`, where validation rejects wildcard CORS, `DEBUG=true`, a `SECRET_KEY` under 32 chars, and rate limiting without `REDIS_URL`.

## Architecture

**Feature modules.** Each module under `app/` (`auth`, `users`, `rbac`, `inventory`, `orders`, `assistant`) owns `router → service → repository → model`, plus `schemas.py`, `dependencies.py` and `exceptions.py`. Single-model modules use `model.py`/`repository.py`; richer ones split into `models/` and `repositories/`.

```
HTTP
 ↓  Router      parse, call the service, return; no business logic
 ↓  Service     business rules, cross-module coordination
 ↓  Repository  SQLAlchemy queries
 ↓  PostgreSQL
```

Cross-module calls: `orders` → `InventoryService` (reserve/release/fulfill), `assistant` → `InventoryService` and `RBACService`, `inventory` → worker `defer_low_stock_alert` (injected as a notifier). `assistant` depends on `inventory` and `rbac`, never the other way around. Known repository reach-ins: `auth` → `UserRepository`, `worker` → `StockRepository`/`UserRepository`.

`app/infra/` holds config, Secrets Manager source, database session, security (passwords, JWT), Redis, rate limiting, mailer (SES) and the LLM client (`infra/llm/client.py` is the only place that imports the Anthropic SDK). `app/common/` holds `AppError`, the exception handlers and the permission/role constants. `app/observability/` holds logging, request ids, Sentry and health checks. `app/bootstraps/` seeds permissions and roles.

Things every request passes through:
- **Transaction**: `get_session` (`app/infra/database/session.py`) commits on success and rolls back on exception. Note that, unlike the docs suggest, many repositories and some services also call `commit()` themselves (`orders.service`, `inventory` repos, `users.repository`, `auth` repos); follow the pattern of the file you are in.
- **Authn**: `get_current_user` in `app/auth/dependencies.py` decodes the access token.
- **Authz**: `require_permission("<resource>:<action>")` from `app/rbac/dependencies.py` runs before the handler and returns 403.
- **Location**: stock and assistant routes need the `X-Location-Id` header (`get_current_location` in `app/inventory/dependencies.py`).
- **Errors**: domain errors extend `AppError` and render as `{error_code, detail}` via `app/common/handlers.py`.
- **Rate limiting**: Redis token bucket (Lua), tight on login/register/password reset and the assistant, tunable with `RATE_LIMIT_OVERRIDES`.

Background work runs in a separate Procrastinate process (`app/worker/`): transactional email and low-stock alerts. Jobs are enqueued only after the commit, and the worker re-reads the row before sending.

### Rules the code never bends

- Order status only moves `CREATED → CONFIRMED → COMPLETED`, or `CONFIRMED → CANCELLED`; items can only be added/removed while `CREATED`.
- Confirm reserves stock per item (`reserved_quantity` goes up), cancel releases it, complete fulfills it. Stock and reservation rows are read `FOR UPDATE`, so the last unit is never sold twice.
- Available stock is `quantity - reserved_quantity`. `low_stock_alerted_at` is set when it drops to `reorder_point` and cleared when it recovers, so an alert fires once per drop; `flush_low_stock_alerts()` is only called after the commit.
- The assistant is read-only. The LLM never computes numbers: restock math lives in `app/inventory/replenishment.py`, tools only call services, and every tool rechecks its permission inside `run_tool`.
- The assistant needs `assistant:use`, runs under `ASSISTANT_DEADLINE_SECONDS`, and charges cost to a per-user daily quota in Redis. If `LLM_MODEL` changes, update the cost weights in `app/assistant/usage.py`.
- Permissions and roles are defined in code (`app/common/constants/`) and seeded; changing them means a re-seed.

## Testing

Integration tests over the real HTTP surface (`httpx.ASGITransport`) against a real, disposable PostgreSQL container on port 5433 (override with `TEST_DATABASE_URL`, never point it at a real db: tables are dropped). `tests/conftest.py` sets the env vars before importing the app and clears the settings cache. Each test gets a fresh schema from `Base.metadata`, rolled back and dropped afterwards; the engine uses `NullPool` to avoid cross-loop asyncpg connections. Rate limit tests use the `redis_enabled` fixture against Redis on 6379 (`TEST_REDIS_URL`). The LLM is faked in the assistant tests.

Fixtures in `tests/conftest.py`: `db_session`, `client`, `seeded`, `admin_user`/`employee_user`/`client_user`/`plain_user`, `auth_headers` (optionally with `X-Location-Id`), and builders (`make_category`, `make_product`, `make_location`, `make_stock`, `make_order`, `make_order_item`) that go through the real endpoints.

Test modules: `tests/auth`, `tests/user`, `tests/rbac`, `tests/inventory`, `tests/order`, `tests/assistant`, `tests/rate_limit`, `tests/observability`. Each covers happy path, validation, permission and edge cases.

## Conventions

- Never access repositories from routers, always go through the service.
- Prefer async everywhere; don't use synchronous SQLAlchemy.
- Use dependency injection over module-level singletons.
- New permissions go in `app/common/constants/`, checked with `require_permission(...)` on the route.
- Don't introduce new architectural patterns, generic base repositories, or abstractions unless something is reused twice.
- Don't create helper functions outside their owning module.
- Keep comments sparse, code and naming should carry the meaning.
