"""
the rbac role-user test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Fixtures and helpers come from integration/conftest.py:
- `admin_user`  : user with the admin role (all permissions)
- `client_user` : user with the client role / no permissions
- `plain_user`  : authenticated user with no role / no permissions
- `auth_headers`: builds the Authorization header for a user
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


# POST rbac/users/{user_id}/roles/{role_id}

# assign role happy path - 201

async def test_assign_role_to_user(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "assignrole")

    response = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 201


# assign role validation - 422

async def test_assign_role_invalid_role_id(
    client, admin_user, plain_user, auth_headers
):
    response = await client.post(
        f"/rbac/users/{plain_user.id}/roles/not-an-int",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 422


# assign role edge cases - 404 not found, 409 duplicate

async def test_assign_role_role_not_found(
    client, admin_user, plain_user, auth_headers
):
    response = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


async def test_assign_role_already_assigned(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "dupeassign")

    first = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert first.status_code == 201

    second = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert second.status_code == 409


# assign role Auth/Permission - 401 and 403

async def test_assign_role_unauthenticated(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "noauthassign")

    response = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
    )
    assert response.status_code == 401


async def test_assign_role_forbidden(
    client, admin_user, client_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "forbiddenassign")

    response = await client.post(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403


# DELETE rbac/users/{user_id}/roles/{role_id}


async def _assign_role(client, admin_user, auth_headers, user_id, role_id):
    """helper: assign a role to a user"""
    response = await client.post(
        f"/rbac/users/{user_id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 201


# remove role happy path - 204

async def test_remove_role_from_user(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "removerole")
    await _assign_role(client, admin_user, auth_headers, plain_user.id, role_id)

    response = await client.delete(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 204


# remove role edge case - 404 not assigned

async def test_remove_role_not_assigned(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "notassignedrole")

    response = await client.delete(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


# remove role Auth/Permission - 401 and 403

async def test_remove_role_unauthenticated(
    client, admin_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "removenoauth")
    await _assign_role(client, admin_user, auth_headers, plain_user.id, role_id)

    response = await client.delete(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
    )
    assert response.status_code == 401


async def test_remove_role_forbidden(
    client, admin_user, client_user, plain_user, auth_headers
):
    role_id = await _create_role(client, admin_user, auth_headers, "removeforbidden")
    await _assign_role(client, admin_user, auth_headers, plain_user.id, role_id)

    response = await client.delete(
        f"/rbac/users/{plain_user.id}/roles/{role_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403
