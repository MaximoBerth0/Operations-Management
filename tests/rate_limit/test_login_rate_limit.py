from app.infra.rate_limit.policy import get_policy


async def test_login_carries_rate_limit_headers(client, plain_user, redis_enabled):
    response = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "password123"},
    )

    assert response.status_code == 200
    assert response.headers["X-RateLimit-Limit"] == str(get_policy("login").capacity)


async def test_login_blocked_after_capacity_exhausted(client, plain_user, redis_enabled):
    capacity = get_policy("login").capacity

    for _ in range(capacity):
        response = await client.post(
            "/auth/login",
            json={"email": plain_user.email, "password": "wrongpassword"},
        )
        assert response.status_code == 401

    blocked = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "wrongpassword"},
    )

    assert blocked.status_code == 429
    assert blocked.headers["X-RateLimit-Remaining"] == "0"
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["detail"]["error_code"] == "RATE_LIMITED"
