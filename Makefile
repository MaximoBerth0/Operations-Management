# The app/containers use host `db` (see .env) from the host using localhost.
LOCAL_DATABASE_URL := postgresql+asyncpg://postgres:postgres@localhost:5432/management

# Run alembic with the local URL injected.
ALEMBIC := DATABASE_URL=$(LOCAL_DATABASE_URL) alembic

# Run procrastinate with the local URL injected.
PROCRASTINATE := DATABASE_URL=$(LOCAL_DATABASE_URL) python -m procrastinate --app=app.worker.app.app

# Compose files now live in docker/.
COMPOSE := docker compose -f docker/docker-compose.yml

.PHONY: db-up db-stop db-down db-reset migrate revision current heads worker-schema worker

db-up:        ## Start the database in the background
	$(COMPOSE) up -d db

db-stop:      ## Stop the database (keeps data)
	$(COMPOSE) stop db

db-down:      ## Remove containers (keeps data volume)
	$(COMPOSE) down

db-reset:     ## Remove containers AND wipe the data volume
	$(COMPOSE) down -v

## Migrations (require the db to be running)
migrate:      ## Apply all pending migrations
	$(ALEMBIC) upgrade head

revision:     ## Autogenerate a migration: make revision m="your message"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

current:      ## Show the DB's current revision
	$(ALEMBIC) current

heads:        ## Show the latest migration file revision
	$(ALEMBIC) heads

## Worker (require the db to be running)
worker-schema: ## Apply the Procrastinate job tables (once, or after an upgrade)
	$(PROCRASTINATE) schema --apply

worker:       ## Run the Procrastinate worker
	$(PROCRASTINATE) worker
