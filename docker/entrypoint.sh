set -eu

# One image, two processes. ROLE=worker runs the queue, anything else serves.
ROLE="${ROLE:-api}"

# Set RUN_MIGRATIONS=false on tasks that must not migrate.
if [ "${ROLE}" = "api" ] && [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    echo "[entrypoint] applying database migrations..."
    alembic upgrade head

    # Procrastinate keeps its own tables outside Alembic, and applying its
    # schema twice is an error, so it goes in only when it is missing.
    if python -m procrastinate --app=app.worker.app.app healthchecks >/dev/null 2>&1; then
        echo "[entrypoint] procrastinate schema already applied"
    else
        echo "[entrypoint] applying procrastinate schema..."
        python -m procrastinate --app=app.worker.app.app schema --apply
    fi
fi

if [ "${ROLE}" = "worker" ]; then
    echo "[entrypoint] starting procrastinate worker..."
    # python -m, not the console script: that one puts its own bin/ on
    # sys.path instead of /app, and app.worker.app is not importable from there
    exec python -m procrastinate --app=app.worker.app.app worker
fi

# number of Gunicorn workers.
WORKERS="${GUNICORN_WORKERS:-${WEB_CONCURRENCY:-4}}"

echo "[entrypoint] starting gunicorn with ${WORKERS} worker(s)..."
exec gunicorn app.main:app \
    --worker-class uvicorn.workers.UvicornWorker \
    --workers "${WORKERS}" \
    --bind 0.0.0.0:8000 \
    --access-logfile - \
    --error-logfile - \
    --timeout 60 \
    --graceful-timeout 30 \
    --keep-alive 5
