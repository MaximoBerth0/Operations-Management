"""The Procrastinate app. Jobs live in Postgres, in their own tables, and the
worker is a separate process from the API:

    python -m procrastinate --app=app.worker.app.app schema --apply   # once
    python -m procrastinate --app=app.worker.app.app worker

`python -m` and not the `procrastinate` console script: that one puts its own
bin/ on sys.path instead of the working directory, and `app.worker.app` is not
importable from there.
"""

import procrastinate

from app.infra.config import settings
from app.observability.sentry import setup_sentry
from app.worker.middleware import job_context_middleware

setup_sentry("worker")


def _conninfo() -> str:
    """SQLAlchemy's asyncpg URL is not a libpq conninfo string, and procrastinate
    talks to Postgres through psycopg."""
    return settings.DATABASE_URL.replace("+asyncpg", "")


app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(conninfo=_conninfo()),
    import_paths=[
        "app.worker.tasks.email",
        "app.worker.tasks.stock_alert",
    ],
    worker_defaults={"worker_middleware": [job_context_middleware]},
)
