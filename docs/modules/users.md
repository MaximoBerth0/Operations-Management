# Users Module

Source: [app/users/](../../app/users/)

## Purpose

Owns the user lifecycle: registration, profile management, and account status (enable/disable) with an audit trail. Authentication ([auth](auth.md)) and role assignment ([rbac](rbac.md)) live in separate modules.

## Architecture

- A `User` has a unique `email` and `username` (both indexed — two lookup paths for auth), a `hashed_password` (raw password never stored), and an `is_active` soft-disable flag checked at auth time.
- Disabling writes an audit trail (`disabled_at`, `disabled_by`, `reason`); enabling clears it.
- Roles are attached many-to-many via the `user_roles` table (owned by rbac), loaded with `selectin` to avoid N+1. Refresh tokens cascade-delete with the user.

Layering is `router → service → repository`; routers never touch the repository directly. The service owns password hashing and all business rules; responses derive from ORM objects and never expose `hashed_password`.

## Flow

**Registration** is public. The service checks email uniqueness *before* insert, raising a typed `UserAlreadyExists` rather than relying on the DB constraint.

**Profile update** (`PUT /users/me`, self-scoped) is partial: only fields the client explicitly sends are updated, and a `forbidden_fields` filter strips anything protected (`id`, `is_active`, timestamps).

**Disable / enable** are admin operations behind **separate** permissions. Disable records who/why/when and flips `is_active = false` atomically in one transaction; enable clears the audit fields for a clean slate.

## Endpoints

All under the `/users` prefix.

| Endpoint | Auth | Permission |
|---|---|---|
| `POST /users/register` | None | — (public) |
| `PUT /users/me` | JWT | — (self-scoped) |
| `GET /users/list` | JWT | `users:view` |
| `GET /users/{user_id}` | JWT | `users:view` |
| `GET /users/email/{email}` | JWT | `users:view` |
| `PATCH /users/{user_id}/disable-account` | JWT | `users:disable` |
| `PATCH /users/{user_id}/enable` | JWT | `users:enable` |

`list` caps its `limit` at 100 server-side regardless of the request.

## Error cases

Extend `UserError` (base 400 / `USER_ERROR`). See [app/users/exceptions.py](../../app/users/exceptions.py).

| Exception | HTTP | Code | When |
|---|---|---|---|
| `UserNotFound` | 404 | `USER_NOT_FOUND` | Lookup by id/email misses |
| `UserAlreadyExists` | 409 | `USER_ALREADY_EXISTS` | Email already registered |
| `UserInactive` | 403 | `USER_INACTIVE` | Account disabled |
