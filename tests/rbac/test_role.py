"""
the rbac module test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Fixtures and helpers come from integration/conftest.py:
- `admin_user`  : user with the admin role (all permissions)
- `plain_user`  : authenticated user with no role / no permissions
- `auth_headers`: builds the Authorization header for a user
"""

import uuid

# POST rbac/roles
 
async def test_create_role(client, admin_user, auth_headers):
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={
            "name": "roletest",
            "description": "new role with a lot of permissions",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "roletest"
    assert body["description"] == "new role with a lot of permissions"


# create role validation - 422

async def test_create_role_name_too_short(client, admin_user, auth_headers):
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"name": "a", "description": "name shorter than 2 chars"},
    )
    assert response.status_code == 422


async def test_create_role_missing_name(client, admin_user, auth_headers):
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"description": "no name field at all"},
    )
    assert response.status_code == 422


async def test_create_role_description_too_long(client, admin_user, auth_headers):
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"name": "longdesc", "description": "x" * 256},
    )
    assert response.status_code == 422


# create role edge case - 409 duplicate

async def test_create_role_duplicate_name(client, admin_user, auth_headers):
    payload = {"name": "dupe_role", "description": "first"}
    first = await client.post(
        "/rbac/roles", headers=auth_headers(admin_user), json=payload
    )
    assert first.status_code == 201

    second = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"name": "dupe_role", "description": "second"},
    )
    assert second.status_code == 409


# create role Auth/Permission - 401 and 403

async def test_create_role_unauthenticated(client):
    response = await client.post(
        "/rbac/roles",
        json={"name": "noauth", "description": "no token provided"},
    )
    assert response.status_code == 401


async def test_create_role_forbidden(client, client_user, auth_headers):
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(client_user),
        json={"name": "forbidden", "description": "user lacks roles:create"},
    )
    assert response.status_code == 403


# PATCH roles/{role_id}


async def _create_role(client, admin_user, auth_headers, name, description="orig"):
    """helper: create a role and return its id"""
    response = await client.post(
        "/rbac/roles",
        headers=auth_headers(admin_user),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()["id"]


# update role happy path - 200

async def test_update_role(client, admin_user, auth_headers):
    role_id = await _create_role(client, admin_user, auth_headers, "before")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"name": "after", "description": "updated"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == role_id
    assert body["name"] == "after"
    assert body["description"] == "updated"


async def test_update_role_partial_name_only(client, admin_user, auth_headers):
    role_id = await _create_role(
        client, admin_user, auth_headers, "partialname", description="keep me"
    )

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"name": "renamed"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "renamed"
    assert body["description"] == "keep me"


async def test_update_role_partial_description_only(client, admin_user, auth_headers):
    role_id = await _create_role(
        client, admin_user, auth_headers, "partialdesc", description="old desc"
    )

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"description": "new desc"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "partialdesc"
    assert body["description"] == "new desc"


# update role validation - 422

async def test_update_role_name_too_short(client, admin_user, auth_headers):
    role_id = await _create_role(client, admin_user, auth_headers, "shortname")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"name": "a"},
    )
    assert response.status_code == 422


async def test_update_role_description_too_long(client, admin_user, auth_headers):
    role_id = await _create_role(client, admin_user, auth_headers, "longdescupd")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"description": "x" * 256},
    )
    assert response.status_code == 422


# update role edge cases - 404 not found, 409 duplicate 
async def test_update_role_not_found(client, admin_user, auth_headers):
    response = await client.patch(
        f"/rbac/roles/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
        json={"name": "ghost"},
    )
    assert response.status_code == 404


async def test_update_role_duplicate_name(client, admin_user, auth_headers):
    await _create_role(client, admin_user, auth_headers, "taken")
    role_id = await _create_role(client, admin_user, auth_headers, "tochange")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(admin_user),
        json={"name": "taken"},
    )
    assert response.status_code == 409


# update role Auth/Permission - 401 and 403

async def test_update_role_unauthenticated(client, admin_user, auth_headers):
    role_id = await _create_role(client, admin_user, auth_headers, "noauthupd")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        json={"name": "noauth"},
    )
    assert response.status_code == 401


async def test_update_role_forbidden(client, admin_user, client_user, auth_headers):
    role_id = await _create_role(client, admin_user, auth_headers, "forbiddenupd")

    response = await client.patch(
        f"/rbac/roles/{role_id}",
        headers=auth_headers(client_user),
        json={"name": "forbidden"},
    )
    assert response.status_code == 403

