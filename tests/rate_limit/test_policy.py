from app.infra.config import RateLimitOverride, settings
from app.infra.rate_limit import policy


def test_get_policy_returns_known_policy():
    login = policy.get_policy("login")
    assert login.name == "login"
    assert login.capacity == 5


def test_get_policy_falls_back_to_default_for_unknown_name():
    unknown = policy.get_policy("does-not-exist")
    assert unknown.name == "default"


def test_build_applies_overrides(monkeypatch):
    monkeypatch.setattr(
        settings,
        "RATE_LIMIT_OVERRIDES",
        {"login": RateLimitOverride(capacity=3, refill_per_second=0.05)},
    )

    built = policy._build()

    assert built["login"].capacity == 3
    assert built["login"].refill_per_second == 0.05
    assert built["register"].capacity == policy._DEFAULTS["register"][0]


def test_build_ignores_unknown_override_name(monkeypatch):
    monkeypatch.setattr(
        settings,
        "RATE_LIMIT_OVERRIDES",
        {"not-a-real-policy": RateLimitOverride(capacity=1, refill_per_second=1.0)},
    )

    built = policy._build()

    assert "not-a-real-policy" not in built
    assert built["login"].capacity == policy._DEFAULTS["login"][0]
