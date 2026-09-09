"""Token bucket, evaluated inside Redis."""

import logging
from dataclasses import dataclass

from redis.exceptions import RedisError

from app.infra.rate_limit.policy import RateLimitPolicy
from app.infra.redis.client import get_client

logger = logging.getLogger(__name__)

KEY_PREFIX = "rl"

# KEYS[1] bucket key
# ARGV[1] capacity  ARGV[2] refill per second  ARGV[3] cost
_CONSUME_LUA = """
local capacity = tonumber(ARGV[1])
local refill   = tonumber(ARGV[2])
local cost     = tonumber(ARGV[3])

local clock = redis.call('TIME')
local now   = tonumber(clock[1]) + tonumber(clock[2]) / 1000000

local state  = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1])
local ts     = tonumber(state[2])

if tokens == nil or ts == nil then
    tokens = capacity
    ts = now
end

local elapsed = now - ts
if elapsed < 0 then
    elapsed = 0
end
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
if tokens >= cost then
    allowed = 1
    tokens = tokens - cost
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], math.ceil(capacity / refill) + 1)

local retry_after = 0
if allowed == 0 then
    retry_after = (cost - tokens) / refill
end

return {allowed, tostring(tokens), tostring(retry_after)}
"""


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    remaining: float
    retry_after: float


async def consume(key: str, policy: RateLimitPolicy, cost: int = 1) -> Decision:
    """Fails open: Redis being down is not a reason to stop serving traffic."""
    client = get_client()
    if client is None:
        return Decision(allowed=True, remaining=float(policy.capacity), retry_after=0.0)

    try:
        allowed, tokens, retry_after = await client.eval(
            _CONSUME_LUA,
            1,
            key,
            policy.capacity,
            policy.refill_per_second,
            cost,
        )
    except (RedisError, OSError) as exc:
        logger.error(
            "rate limit check failed, allowing the request",
            extra={
                "policy": policy.name,
                "reason": str(exc),
                "exception": type(exc).__name__,
            },
        )
        return Decision(allowed=True, remaining=float(policy.capacity), retry_after=0.0)

    return Decision(
        allowed=bool(allowed),
        remaining=float(tokens),
        retry_after=float(retry_after),
    )


def build_key(policy_name: str, identity: str) -> str:
    return f"{KEY_PREFIX}:{policy_name}:{identity}"
