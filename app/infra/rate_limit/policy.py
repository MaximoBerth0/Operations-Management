"""Per-endpoint token bucket limits: capacity is the burst, refill_per_second
is the sustained rate. RATE_LIMIT_OVERRIDES retunes named policies in prod
without a redeploy."""

import logging
from dataclasses import dataclass

from app.infra.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    name: str
    capacity: int
    refill_per_second: float

    @property
    def recovery_seconds(self) -> float:
        return self.capacity / self.refill_per_second


_DEFAULTS: dict[str, tuple[int, float]] = {
    "login": (5, 0.1),
    "register": (5, 0.1),
    "password_reset": (3, 0.05),
    "token_refresh": (30, 1.0),
    "default": (120, 20.0),
}


def _build() -> dict[str, RateLimitPolicy]:
    policies: dict[str, RateLimitPolicy] = {}

    for name, (capacity, refill) in _DEFAULTS.items():
        override = settings.RATE_LIMIT_OVERRIDES.get(name)
        if override is not None:
            capacity = override.capacity or capacity
            refill = override.refill_per_second or refill
            logger.info(
                "rate limit policy overridden",
                extra={"policy": name, "capacity": capacity, "refill_per_second": refill},
            )
        policies[name] = RateLimitPolicy(
            name=name, capacity=capacity, refill_per_second=refill
        )

    for unknown in settings.RATE_LIMIT_OVERRIDES.keys() - _DEFAULTS.keys():
        logger.error(
            "RATE_LIMIT_OVERRIDES names a policy that does not exist",
            extra={"policy": unknown},
        )

    return policies


POLICIES = _build()


def get_policy(name: str) -> RateLimitPolicy:
    policy = POLICIES.get(name)
    if policy is None:
        logger.error("unknown rate limit policy requested", extra={"policy": name})
        return POLICIES["default"]

    return policy
