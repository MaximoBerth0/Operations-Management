# RBAC Module

Source: [app/rbac/](../../app/rbac/)

## Purpose

Role-Based Access Control. Users get permissions **through roles**, never directly. Permissions are enforced by a FastAPI dependency that runs before a protected endpoint executes.

## Architecture

```
┌─────────┐  M:N   ┌─────────┐  M:N   ┌─────────────┐
│  Users  │───────▶│  Roles  │───────▶│ Permissions │
└─────────┘        └─────────┘        └─────────────┘

User → has roles → roles have permissions → check passes / fails
```

- Two association tables with composite PKs and cascading deletes: `user_roles` (User ↔ Role) and `role_permissions` (Role ↔ Permission).
- Permissions use a `resource:action` code convention (e.g. `users:view`, `stock:in`).
- **Permission matrices live in code, not the DB.** `seed_all()` runs once at startup ([app/bootstraps/](../../app/bootstraps/)) to create every permission then assign them to the seeded roles `admin`, `employee`, `client` (see [app/core/constants/](../../app/core/constants/)). `client` is intentionally permission-less — its access comes from self-scoped and public routes, not RBAC grants. Changing the matrix means a re-seed.

## Flow

Every protected request passes through the `require_permission(code)` dependency:

```
request → get_current_user (from JWT) → require_permission(code)
        → ensure_permission(user_id, code)
              ├─ load user.roles → permissions in ONE query
              ├─ any permission.code == code?  → allow
              └─ else                          → 403 PermissionDenied
```

**The token `roles` claim is not trusted for authorization.** `ensure_permission` re-loads roles and permissions from the DB on every call, so a revoked role or permission takes effect immediately rather than at next token refresh. The claim is informational only.

## Endpoints

All under the `/rbac` prefix; every route is permission-gated.

| Endpoint | Permission |
|---|---|
| `POST /rbac/roles` | `roles:create` |
| `PATCH /rbac/roles/{role_id}` | `roles:update` |
| `GET /rbac/roles` | `roles:view` |
| `POST /rbac/roles/{role_id}/permissions` | `role:assign_permission` |
| `DELETE /rbac/roles/{role_id}/permissions` | `role:remove_permission` |
| `POST /rbac/users/{user_id}/roles/{role_id}` | `users:assign_role` |
| `DELETE /rbac/users/{user_id}/roles/{role_id}` | `users:remove_role` |

## Error cases

Extend `RbacError` (base 400 / `RBAC_ERROR`). See [app/rbac/exceptions.py](../../app/rbac/exceptions.py).

| Exception | HTTP | Code | When |
|---|---|---|---|
| `RoleNotFound` | 404 | `ROLE_NOT_FOUND` | Role id/name misses |
| `RoleAlreadyExists` | 409 | `ROLE_ALREADY_EXISTS` | Duplicate role name |
| `PermissionNotFound` | 404 | `PERMISSION_NOT_FOUND` | Permission id misses |
| `PermissionAlreadyAssigned` | 409 | `PERMISSION_ALREADY_ASSIGNED` | Permission already on the role |
| `RoleAlreadyAssignedToUser` | 409 | `ROLE_ALREADY_ASSIGNED_TO_USER` | User already has the role |
| `UserRoleNotFound` | 404 | `USER_ROLE_NOT_FOUND` | Removing a role the user lacks |
| `RolePermissionNotFound` | 404 | `ROLE_PERMISSION_NOT_FOUND` | Removing a permission the role lacks |
| `PermissionDenied` | 403 | `PERMISSION_DENIED` | Authorization check fails |
