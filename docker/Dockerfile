# single source of truth for the interpreter version across both stages
ARG PYTHON_VERSION=3.14.5

# builder
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VERSION=1.8.3 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

WORKDIR /app

# build deps needed to compile any wheels (argon2-cffi, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install "poetry==${POETRY_VERSION}"

COPY pyproject.toml poetry.lock ./

# install ONLY the locked runtime deps into ./.venv (no dev deps, no project root)
RUN poetry install --only main --no-root

# runtime
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    GUNICORN_WORKERS=4

# Sentry release
ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# bring over only the virtualenv — no build tools, no poetry, no apt caches
COPY --from=builder /app/.venv /app/.venv

# non-root user
RUN useradd --create-home --uid 1000 appuser

COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker/entrypoint.sh ./entrypoint.sh

USER appuser

EXPOSE 8000

# Container-level health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else sys.exit(1)"]

# tini as PID 1 → entrypoint runs migrations, then execs gunicorn.
ENTRYPOINT ["tini", "--", "./entrypoint.sh"]