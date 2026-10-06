# System Map

Quick tour of what this thing is, what you can do with it, and where stuff lives. For the deeper version, see [architecture](architecture.md) and the [module docs](modules/).

## TL;DR

A back-office API for a business: you have products sitting in locations, people place orders, the orders reserve stock, and when stock runs low someone gets an email. Who can do what is decided by roles and permissions.

```
                    ┌──────────────┐
  client / admin ──▶│   FastAPI    │──▶ PostgreSQL (everything, incl. job queue)
                    │  (app/main)  │──▶ Redis (rate limiting)
                    └──────┬───────┘
                           │ enqueue jobs (after commit)
                           ▼
                    ┌──────────────┐
                    │ Procrastinate│──▶ SES (emails)
                    │    worker    │
                    └──────────────┘
```

## The pieces

| Module | What it's for | Prefix |
|---|---|---|
| `auth` | login, refresh, logout, password reset/change | `/auth` |
| `users` | register, profile, list users, enable/disable accounts | `/users` |
| `rbac` | roles, permissions, who has which role | `/rbac` |
| `inventory` | products, categories, locations, stock and movements | `/inventory` |
| `orders` | create orders, add items, confirm/cancel/complete | `/orders` |
| `observability` | health checks, request ids, logging | `/health` |
| `worker` | background jobs (emails, low stock alerts) | n/a |
| `infra` | config, DB session, Redis, mailer, JWT/passwords, rate limit | n/a |

Every feature module has the same shape: `router → service → repository → model`. Learn one, you know them all.

## What can you actually do?

### As anyone (no login)
- Register an account (`POST /users/register`)
- Log in and get tokens (`POST /auth/login`)
- Ask for a password reset email (`/auth/forgot`, then `/auth/reset`)
- Look up an order by its code (`GET /orders/code/{code}`)

### As a logged in user (any role, including `client`)
- Update your profile (`PUT /users/me`)
- See your own orders (`GET /orders/me`)
- Refresh your session, log out, change your password

### As an `employee`
Everything above, plus:
- Create and edit products, put them in categories
- Move stock: `in` (receive), `out` (ship/lose), `adjust` (fix counts), and check stock and movement history
- View locations
- Run the full order flow: create, add/remove items, confirm, cancel, complete

### As an `admin`
Everything. On top of the employee stuff:
- Deactivate/activate products, delete categories
- Create stock records and manage locations
- Manage users (list, disable, enable)
- Manage roles and permissions, assign roles to users
- Receive low stock alert emails (`stock:alert`)

Roles are defined in [system_roles.py](../app/common/constants/system_roles.py) and seeded with the bootstrap script. Permissions are plain strings like `order:confirm`, checked by `require_permission(...)` on each route.

## The main flow: an order's life

```
created ──confirm──▶ confirmed ──complete──▶ completed
   │                     │
   └──────cancel─────────┴──────▶ cancelled
```

What happens to stock at each step:

| Step | Order | Stock at the chosen location |
|---|---|---|
| create + add items | `created` | nothing yet, it's just a cart |
| confirm | `confirmed` | a reservation per item, `reserved_quantity` goes up |
| cancel | `cancelled` | reservations released, stock is available again |
| complete | `completed` | reservations fulfilled, stock actually leaves |

Reservations lock the stock row, so two orders can't grab the same last unit.

## Low stock alerts

Each stock row has a `reorder_point`. When available stock (quantity minus reserved) drops to or below it:

1. The service marks the row with `low_stock_alerted_at` (so it only fires once per drop).
2. After the commit, it enqueues a `low_stock_alert` job.
3. The worker re-reads the row. If it already recovered, nothing is sent.
4. Otherwise it sends one email per user with `stock:alert` (admins by default).

When stock goes back above the threshold the flag is cleared, so the next drop alerts again.

## Other stuff worth knowing

- **Auth:** JWT access token + refresh token with rotation. Logout revokes the refresh token.
- **Rate limiting:** token bucket in Redis (Lua script). Tight limits on login, register and password reset, looser default for the rest. Tunable in prod via `RATE_LIMIT_OVERRIDES`.
- **Errors:** every domain error extends `AppError` and comes back as `{error_code, detail}`.
- **Background jobs:** Procrastinate, which uses Postgres as the queue. No extra broker needed.
- **Prod:** ECS Fargate behind an ALB, RDS Postgres, Secrets Manager, SES. See [deployment](deployment.md).

## Running it locally

```bash
docker compose -f docker/docker-compose.yml up --build   # API + Postgres
make worker-schema                                       # once, job tables
make worker                                              # background worker
```

Then open `http://localhost:8000/docs` for Swagger. Don't forget to run the bootstrap seed so roles and permissions exist (see the [README](../README.md)).

## Where to look when...

| You want to... | Go to |
|---|---|
| add an endpoint | `app/<module>/router.py`, then `service.py` |
| change who can do what | `app/common/constants/` + re-seed |
| touch the order/stock logic | `app/orders/service.py`, `app/inventory/service.py` |
| add a background job | `app/worker/tasks/` |
| change config or secrets | `app/infra/config.py`, `env.example` |
| add a migration | `make revision m="..."`, then `make migrate` |
| run tests | see [testing](testing.md) |
