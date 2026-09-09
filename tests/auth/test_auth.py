"""
the auth module test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Fixtures and helpers come from integration/conftest.py:
- `admin_user`  : user with the admin role (all permissions)
- `plain_user`  : authenticated user with no role / no permissions
- `auth_headers`: builds the Authorization header for a user
"""

from datetime import datetime, timedelta, timezone

from app.auth.model import PasswordResetToken

# POST /auth/login

async def test_login_success(client, plain_user):
    response = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "password123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password(client, plain_user):
    response = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "wrongpassword"},
    )
    assert response.status_code == 401


async def test_login_unknown_email(client):
    response = await client.post(
        "/auth/login",
        json={"email": "nobody@test.com", "password": "password123"},
    )
    assert response.status_code == 401


async def test_login_invalid_email(client):
    response = await client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "password123"},
    )
    assert response.status_code == 422


async def test_login_short_password(client):
    response = await client.post(
        "/auth/login",
        json={"email": "user@test.com", "password": "short"},
    )
    assert response.status_code == 422


# POST /auth/change-password

async def test_change_password_success(client, plain_user, auth_headers):
    response = await client.post(
        "/auth/change-password",
        json={"old_password": "password123", "new_password": "newpassword123"},
        headers=auth_headers(plain_user),
    )
    assert response.status_code == 204

    # the new password works
    ok = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "newpassword123"},
    )
    assert ok.status_code == 200

    # the old password no longer works
    stale = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "password123"},
    )
    assert stale.status_code == 401


async def test_change_password_wrong_old_password(client, plain_user, auth_headers):
    response = await client.post(
        "/auth/change-password",
        json={"old_password": "wrongpassword", "new_password": "newpassword123"},
        headers=auth_headers(plain_user),
    )
    assert response.status_code == 401


async def test_change_password_unauthenticated(client):
    response = await client.post(
        "/auth/change-password",
        json={"old_password": "password123", "new_password": "newpassword123"},
    )
    assert response.status_code == 401


# POST /auth/reset

async def _make_reset_token(db_session, user_id, *, token, minutes=10):
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    reset = PasswordResetToken(
        user_id=user_id,
        token=token,
        expires_at=expires_at,
        used=False,
    )
    db_session.add(reset)
    await db_session.commit()
    return reset


async def test_reset_password_success(client, db_session, plain_user):
    await _make_reset_token(db_session, plain_user.id, token="valid-reset-token")

    response = await client.post(
        "/auth/reset",
        json={"token": "valid-reset-token", "new_password": "resetpassword123"},
    )
    assert response.status_code == 204

    # the new password works
    ok = await client.post(
        "/auth/login",
        json={"email": plain_user.email, "password": "resetpassword123"},
    )
    assert ok.status_code == 200


async def test_reset_password_invalid_token(client):
    response = await client.post(
        "/auth/reset",
        json={"token": "does-not-exist", "new_password": "resetpassword123"},
    )
    assert response.status_code == 401


async def test_reset_password_expired_token(client, db_session, plain_user):
    await _make_reset_token(
        db_session, plain_user.id, token="expired-reset-token", minutes=-10
    )

    response = await client.post(
        "/auth/reset",
        json={"token": "expired-reset-token", "new_password": "resetpassword123"},
    )
    assert response.status_code == 401


# disabled accounts — every path back in must stay closed
#
# `is_active` is derived from `disabled_at`, so these all hinge on the audit
# trail rather than on a stored boolean.

async def test_login_disabled_account(client, disabled_user):
    response = await client.post(
        "/auth/login",
        json={"email": disabled_user.email, "password": "password123"},
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "ACCOUNT_DISABLED"


async def test_disabled_account_rejected_on_protected_endpoint(
    client, disabled_user, auth_headers
):
    # a valid, unexpired token for an account disabled after it was issued
    response = await client.get("/users/list", headers=auth_headers(disabled_user))
    assert response.status_code == 403
    assert response.json()["error_code"] == "ACCOUNT_DISABLED"


async def test_disable_revokes_access_mid_session(
    client, employee_user, admin_user, auth_headers
):
    """Disabling must take effect immediately, not when the access token expires."""
    login = await client.post(
        "/auth/login",
        json={"email": employee_user.email, "password": "password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    # the session works while the account is active. NB: probe with an endpoint
    # that does not revoke refresh tokens — change-password does, which would
    # invalidate the token this test checks below.
    before = await client.put(
        "/users/me", json={"username": "still_here"}, headers=headers
    )
    assert before.status_code == 200

    disable = await client.patch(
        f"/users/{employee_user.id}/disable-account",
        json={"reason": "Policy violation"},
        headers=auth_headers(admin_user),
    )
    assert disable.status_code == 200

    # the same access token is now dead
    after = await client.put(
        "/users/me", json={"username": "sneaking_back"}, headers=headers
    )
    assert after.status_code == 403
    assert after.json()["error_code"] == "ACCOUNT_DISABLED"

    # and the refresh token cannot mint a new one
    refreshed = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refreshed.status_code == 403
    assert refreshed.json()["error_code"] == "ACCOUNT_DISABLED"


async def test_reset_password_disabled_account(client, db_session, disabled_user):
    """A reset token issued before disabling must not let the user back in."""
    await _make_reset_token(db_session, disabled_user.id, token="disabled-reset-token")

    response = await client.post(
        "/auth/reset",
        json={"token": "disabled-reset-token", "new_password": "resetpassword123"},
    )
    assert response.status_code == 403

    # the password was not changed, so the new one is simply wrong credentials
    login = await client.post(
        "/auth/login",
        json={"email": disabled_user.email, "password": "resetpassword123"},
    )
    assert login.status_code == 401

    # and the original one still hits the disabled check
    original = await client.post(
        "/auth/login",
        json={"email": disabled_user.email, "password": "password123"},
    )
    assert original.status_code == 403


async def test_forgot_password_disabled_account_is_silent(client, disabled_user):
    """Same 204 as an unknown address — no reset mail, no account enumeration."""
    response = await client.post(
        "/auth/forgot",
        json={"email": disabled_user.email},
    )
    assert response.status_code == 204


async def test_login_after_re_enable(client, disabled_user, admin_user, auth_headers):
    enabled = await client.patch(
        f"/users/{disabled_user.id}/enable", headers=auth_headers(admin_user)
    )
    assert enabled.status_code == 200

    response = await client.post(
        "/auth/login",
        json={"email": disabled_user.email, "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
