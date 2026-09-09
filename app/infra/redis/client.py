"""The Redis connection, owned in one place the way the engine is."""

import logging

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from app.infra.config import settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_client() -> Redis | None:
    return _client


async def startup() -> None:
    global _client

    if not settings.REDIS_URL:
        logger.warning("REDIS_URL is empty, every Redis-backed feature stays off")
        return

    pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        socket_connect_timeout=settings.REDIS_CONNECT_TIMEOUT,
        socket_timeout=settings.REDIS_COMMAND_TIMEOUT,
        health_check_interval=30,
        decode_responses=True,
    )
    client = Redis(connection_pool=pool)

    await client.ping()
    _client = client
    logger.info("redis reachable")


async def shutdown() -> None:
    global _client

    if _client is None:
        return

    await _client.aclose()
    _client = None
    logger.info("redis connection pool disposed")


async def ping() -> bool:
    if _client is None:
        return False

    try:
        await _client.ping()
    except (RedisError, OSError) as exc:
        logger.error("redis ping failed", extra={"reason": str(exc)})
        return False

    return True
