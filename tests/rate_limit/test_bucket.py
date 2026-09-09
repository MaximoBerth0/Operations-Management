import asyncio

from app.infra.rate_limit import bucket
from app.infra.rate_limit.policy import RateLimitPolicy


async def test_consume_allows_within_capacity(redis_enabled):
    policy = RateLimitPolicy(name="test_within", capacity=3, refill_per_second=1.0)
    key = bucket.build_key(policy.name, "ip:1.2.3.4")

    for _ in range(3):
        decision = await bucket.consume(key, policy)
        assert decision.allowed is True

    assert (await bucket.consume(key, policy)).allowed is False


async def test_consume_blocks_over_capacity_and_reports_retry_after(redis_enabled):
    policy = RateLimitPolicy(name="test_over", capacity=1, refill_per_second=0.1)
    key = bucket.build_key(policy.name, "ip:1.2.3.4")

    assert (await bucket.consume(key, policy)).allowed is True

    decision = await bucket.consume(key, policy)
    assert decision.allowed is False
    assert decision.retry_after > 0


async def test_consume_refills_over_time(redis_enabled):
    policy = RateLimitPolicy(name="test_refill", capacity=1, refill_per_second=20.0)
    key = bucket.build_key(policy.name, "ip:1.2.3.4")

    assert (await bucket.consume(key, policy)).allowed is True
    assert (await bucket.consume(key, policy)).allowed is False

    await asyncio.sleep(0.1)

    assert (await bucket.consume(key, policy)).allowed is True


async def test_consume_fails_open_without_client(monkeypatch):
    monkeypatch.setattr(bucket, "get_client", lambda: None)
    policy = RateLimitPolicy(name="test_no_client", capacity=5, refill_per_second=1.0)

    decision = await bucket.consume("some-key", policy)

    assert decision.allowed is True
    assert decision.remaining == 5


def test_build_key_namespaces_by_policy_and_identity():
    assert bucket.build_key("login", "ip:1.2.3.4") == "rl:login:ip:1.2.3.4"
