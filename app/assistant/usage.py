"""Token cost of a chat and the per-user daily quota in Redis.

Cost is measured in units of one uncached input token, so cached reads are
cheap and output is expensive, matching the bill instead of raw token counts."""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from redis.exceptions import RedisError

from app.infra.llm.client import LLMUsage
from app.infra.redis.client import get_client

logger = logging.getLogger(__name__)

# Claude Opus 5.5 prices relative to uncached input ($4/MTok)
CACHE_READ_WEIGHT = 0.05
CACHE_WRITE_WEIGHT = 1.25
OUTPUT_WEIGHT = 5.0

KEY_PREFIX = "assistant:usage"
KEY_TTL_SECONDS = 2 * 24 * 3600


@dataclass
class UsageMeter:
    """Mutable on purpose: it outlives a cancelled loop so a timeout is still charged."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, usage: LLMUsage) -> None:
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cache_read_input_tokens += usage.cache_read_input_tokens
        self.cache_creation_input_tokens += usage.cache_creation_input_tokens

    @property
    def cost_units(self) -> int:
        return round(
            self.input_tokens
            + self.cache_read_input_tokens * CACHE_READ_WEIGHT
            + self.cache_creation_input_tokens * CACHE_WRITE_WEIGHT
            + self.output_tokens * OUTPUT_WEIGHT
        )


def _key(user_id: uuid.UUID) -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"{KEY_PREFIX}:{user_id}:{day}"


async def used_today(user_id: uuid.UUID) -> int:
    """Fails open like the rate limit: 0 when Redis is off or down."""
    client = get_client()
    if client is None:
        return 0

    try:
        value = await client.get(_key(user_id))
    except (RedisError, OSError) as exc:
        logger.error(
            "assistant quota check failed, allowing the request",
            extra={"user_id": user_id, "reason": str(exc), "exception": type(exc).__name__},
        )
        return 0

    return int(value or 0)


async def charge(user_id: uuid.UUID, cost_units: int) -> None:
    client = get_client()
    if client is None or cost_units <= 0:
        return

    key = _key(user_id)
    try:
        async with client.pipeline(transaction=True) as pipe:
            pipe.incrby(key, cost_units)
            pipe.expire(key, KEY_TTL_SECONDS)
            await pipe.execute()
    except (RedisError, OSError) as exc:
        logger.error(
            "assistant quota charge failed",
            extra={"user_id": user_id, "cost_units": cost_units, "reason": str(exc), "exception": type(exc).__name__},
        )
