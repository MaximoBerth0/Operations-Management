import os

import pytest_asyncio

from app.infra.config import settings
from app.infra.redis import client as redis_client_module

TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/0")


@pytest_asyncio.fixture
async def redis_enabled(monkeypatch):
    monkeypatch.setattr(settings, "REDIS_URL", TEST_REDIS_URL)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)

    await redis_client_module.startup()
    client = redis_client_module.get_client()
    await client.flushdb()

    yield client

    await client.flushdb()
    await redis_client_module.shutdown()
