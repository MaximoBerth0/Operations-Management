# Architecture

## Overview

The Management API is a single FastAPI application, organized as a set of **feature modules** ([auth](modules/auth.md), [users](modules/users.md), [rbac](modules/rbac.md), [inventory](modules/inventory.md), [orders](modules/orders.md)) over a shared PostgreSQL database, accessed asynchronously via SQLAlchemy + asyncpg. It ships as one container image and runs on AWS ECS Fargate (see [deployment](deployment.md)).

Cross-cutting concerns live outside the feature modules: configuration, security primitives, and the global error contract in `app/core/`; the async engine and session in `app/database/`; request-id, logging, and health probes in `app/observability/`.

## Layer division

Every feature module follows the same four-layer split, wired together by FastAPI dependency injection. Requests only ever flow downward:

```
Router        HTTP surface — path/verb, request/response schemas.
  │           Thin: parse, call the service, return. No business logic.
  ▼
Service       Business logic — validation, orchestration, transactions.
  │           Owns cross-module coordination (e.g. orders → inventory).
  ▼
Repository    Data access — one SQLAlchemy operation per method.
  │           No business rules, no HTTP awareness.
  ▼
Model         SQLAlchemy ORM entities + domain invariants
              (e.g. Order state-machine guards).
```

Rules that keep the layers honest:

- **Routers never touch repositories** — they go through the service.
- **Services own transactions.** A service method that spans multiple writes (or multiple modules) commits once at the end so the changes persist or roll back together.
- **Errors are typed.** Each module raises domain exceptions extending a shared `AppError`; a single handler in `app/main.py` renders them as `{error_code, detail}` with the right status. No raw `ValueError`s reach the client.
- **Authorization is a dependency.** `require_permission(...)` runs before the route handler; the handler never executes on a failed check (see [rbac](modules/rbac.md)).

## Folder structure

```
app/
├── main.py              # FastAPI app: middleware, error handlers, router wiring
│
├── auth/                # feature module (see modules/auth.md)
├── users/               # feature module
├── rbac/                # feature module
├── inventory/           # feature module
├── orders/              # feature module
│   ├── router.py        #   HTTP layer
│   ├── service.py       #   business logic
│   ├── repository.py    #   data access   (or repositories/ when split)
│   ├── models/          #   ORM entities  (or model.py for single-model modules)
│   ├── schemas.py       #   Pydantic request/response models
│   ├── dependencies.py  #   FastAPI DI wiring for this module
│   └── exceptions.py    #   typed domain errors
│
├── core/                # cross-cutting foundations
│   ├── config.py        #   Settings (pydantic-settings, layered sources)
│   ├── secrets.py       #   AWS Secrets Manager settings source
│   ├── security/        #   password hashing + JWT tokens
│   ├── constants/       #   permission/role matrices (seeded at startup)
│   └── global_errors.py #   AppError base + error contract
│
├── database/            # async engine, session factory, lifecycle hooks
├── observability/       # request-id middleware, logging setup, health probes
├── mail/                # SES-backed mailer
└── bootstraps/          # one-off seeders (permissions, roles)

alembic/                 # database migrations
docker/                  # Dockerfile, entrypoint, compose files
deploy/                  # ECS task definition + AWS deploy guide
docs/                    # this documentation
```

Single-model modules (auth, users) use `model.py` and `repository.py`; richer modules (inventory, orders, rbac) split into `models/` and `repositories/` packages. The shape is otherwise identical, so any module is navigable once you know one.
