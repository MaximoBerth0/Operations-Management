# Auth Module

Source: [app/auth/](../../app/auth/)

## Purpose

JWT-based authentication. Users log in with email/password and receive a short-lived **access token** plus a long-lived **refresh token**. Password reset runs over email with a time-limited, single-use token. Role names are embedded in the access token so RBAC checks can read them without a DB round-trip (see [rbac](rbac.md)).

## Architecture

```
┌─────────┐   JWT     ┌───────────────┐  verify  ┌──────────────────────┐
│  Client │──────────▶│  Access Token │─────────▶│  get_current_user()  │
└─────────┘           └───────────────┘          └──────────────────────┘

┌─────────┐   opaque  ┌───────────────┐  rotate  ┌──────────────────────┐
│  Client │──────────▶│ Refresh Token │─────────▶│  refresh_session()   │
└─────────┘           └───────────────┘          └──────────────────────┘
```

- **Access token** — short-lived JWT, verified statelessly. Carries `sub`, `type`, `iat`, `exp`, `jti`, and a `roles` claim (list of role names).
- **Refresh token** — opaque random string; only its SHA-256 hash is stored, so it can be revoked at any time.
- **Password reset token** — single-use, expires in 10 minutes.
- Passwords are hashed with Argon2 (`argon2-cffi`).

## Flow

**Login** — verify credentials → issue access JWT (with `roles`) → persist a hashed refresh token → return both.

**Refresh** — look up the active refresh token → check expiry → **rotate** (revoke old, issue new) → re-fetch user and re-embed current roles (so role changes take effect on refresh) → return both.

**Password reset** — `forgot` finds the user (silent on unknown email to prevent enumeration), invalidates prior reset tokens, stores a fresh 10-min token, and emails it. `reset` validates the token, sets the new password, and **revokes all refresh tokens** (forces re-login everywhere). `change-password` does the same revocation after verifying the old password.

## Endpoints

All under the `/auth` prefix.

| Endpoint | Auth | Result |
|---|---|---|
| `POST /auth/login` | None | Access + refresh tokens |
| `POST /auth/refresh` | None | Rotates refresh token, new access token |
| `POST /auth/logout` | None | Revokes refresh token (204) |
| `POST /auth/forgot` | None | Sends reset email; silent on unknown email (204) |
| `POST /auth/reset` | None | Consumes reset token, sets new password (204) |
| `POST /auth/change-password` | JWT | Requires old password (204) |

## Error cases

All extend `AuthError` (base HTTP 401). See [app/auth/exceptions.py](../../app/auth/exceptions.py).

| Exception | HTTP | Code | When |
|---|---|---|---|
| `InvalidCredentials` | 401 | `INVALID_CREDENTIALS` | Wrong email or password (intentionally conflated) |
| `TokenExpired` | 401 | `TOKEN_EXPIRED` | Refresh/reset token stale or not found |
| `TokenInvalid` | 401 | `TOKEN_INVALID` | Bad signature, wrong token type, or already-revoked token |
