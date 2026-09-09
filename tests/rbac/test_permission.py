"""
the rbac role-permission test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Fixtures and helpers come from integration/conftest.py:
- `admin_user`  : user with the admin role (all permissions)
- `client_user` : user with the client role / no permissions
- `auth_headers`: builds the Authorization header for a user
- `seeded`      : inserts all permissions/roles, returns their objects
"""

import uuid


async def _create_role(client, admin_user, auth_headers, name, description="orig"):
    """helper: create a role and return its id"""
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _a_permission_id(seeded):
    """helper: return the id of an arbitrary seeded permission"""
    return str(next(iter(seeded["permissions"].values())).id)


# POST rbac/roles/{role_id}/permissions

# assign permission happy path - 201

async def test_assign_permission_to_role(client, admin_user, auth_headers, seeded):
    role_id = await _create_role(client, admin_user, auth_headers, "withperm")
    permission_id = _a_permission_id(seeded)

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 201


# assign permission validation - 422

async def test_assign_permission_missing_permission_id(
    client, admin_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "missingperm")

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={},
    )
    assert response.status_code == 422


async def test_assign_permission_invalid_permission_id(
    client, admin_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "invalidperm")

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": "not-an-int"},
    )
    assert response.status_code == 422


# assign permission edge cases - 404 not found, 409 duplicate

async def test_assign_permission_role_not_found(
    client, admin_user, auth_headers, seeded
):
    permission_id = _a_permission_id(seeded)

    response = await client.post(
        f"/rbac/roles/{uuid.uuid4()}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 404


async def test_assign_permission_permission_not_found(
    client, admin_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "ghostperm")

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404


async def test_assign_permission_already_assigned(
    client, admin_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "dupeperm")
    permission_id = _a_permission_id(seeded)

    first = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert second.status_code == 409


# assign permission Auth/Permission - 401 and 403

async def test_assign_permission_unauthenticated(
    client, admin_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "noauthperm")
    permission_id = _a_permission_id(seeded)

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        json={"permission_id": permission_id},
    )
    assert response.status_code == 401


async def test_assign_permission_forbidden(
    client, admin_user, client_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "forbiddenperm")
    permission_id = _a_permission_id(seeded)

    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(client_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 403


# DELETE rbac/roles/{role_id}/permissions


async def _assign_permission(client, admin_user, auth_headers, role_id, permission_id):
    """helper: assign a permission to a role"""
    response = await client.post(
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 201


# remove permission happy path - 204

async def test_remove_permission_from_role(client, admin_user, auth_headers, seeded):
    role_id = await _create_role(client, admin_user, auth_headers, "removeperm")
    permission_id = _a_permission_id(seeded)
    await _assign_permission(client, admin_user, auth_headers, role_id, permission_id)

    response = await client.request(
        "DELETE",
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 204


# remove permission validation - 422

async def test_remove_permission_missing_permission_id(
    client, admin_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "removemissing")

    response = await client.request(
        "DELETE",
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={},
    )
    assert response.status_code == 422


# remove permission edge case - 404 not assigned

async def test_remove_permission_not_assigned(
    client, admin_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "notassigned")
    permission_id = _a_permission_id(seeded)

    response = await client.request(
        "DELETE",
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(admin_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 404


# remove permission Auth/Permission - 401 and 403

async def test_remove_permission_unauthenticated(
    client, admin_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "removenoauth")
    permission_id = _a_permission_id(seeded)
    await _assign_permission(client, admin_user, auth_headers, role_id, permission_id)

    response = await client.request(
        "DELETE",
        f"/rbac/roles/{role_id}/permissions",
        json={"permission_id": permission_id},
    )
    assert response.status_code == 401


async def test_remove_permission_forbidden(
    client, admin_user, client_user, auth_headers, seeded
):
    role_id = await _create_role(client, admin_user, auth_headers, "removeforbidden")
    permission_id = _a_permission_id(seeded)
    await _assign_permission(client, admin_user, auth_headers, role_id, permission_id)

    response = await client.request(
        "DELETE",
        f"/rbac/roles/{role_id}/permissions",
        headers=auth_headers(client_user),
        json={"permission_id": permission_id},
    )
    assert response.status_code == 403
