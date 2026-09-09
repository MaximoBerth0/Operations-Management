"""
the location file test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Locations are created through the API (POST /inventory/locations), gated by
`location:create` (admin only). Listing is gated by `location:list`, which both
admin and employee have.

Fixtures and helpers come from integration/conftest.py:
- `admin_user`    : user with the admin role (all permissions)
- `employee_user` : user with the employee role (can list, cannot create)
- `client_user`   : user with the client role (no permissions)
- `auth_headers`  : builds the Authorization header for a user
"""

import uuid


async def _create_location(client, admin_user, auth_headers, name, city="metropolis", address="123 st"):
    """helper: create a location and return its id"""
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": name, "city": city, "address": address},
    )
    assert response.status_code == 201
    return response.json()["id"]

# GET /inventory/locations


async def test_list_locations(client, admin_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.get(
        "/inventory/locations",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    ids = [location["id"] for location in body["items"]]
    assert location_id in ids
    assert body["total"] == len(body["items"])


async def test_list_locations_employee_allowed(client, admin_user, employee_user, auth_headers):
    # employees can see locations even though they cannot create them
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.get(
        "/inventory/locations",
        headers=auth_headers(employee_user),
    )
    assert response.status_code == 200
    ids = [location["id"] for location in response.json()["items"]]
    assert location_id in ids


async def test_list_locations_empty(client, admin_user, auth_headers):
    response = await client.get(
        "/inventory/locations",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_locations_forbidden(client, client_user, auth_headers):
    response = await client.get(
        "/inventory/locations",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403

# POST /inventory/locations


async def test_create_location(client, admin_user, auth_headers):
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": "warehouse", "city": "metropolis", "address": "1 Industrial Rd"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "warehouse"
    assert body["city"] == "metropolis"
    assert body["address"] == "1 Industrial Rd"
    assert "id" in body


async def test_create_location_missing_address(client, admin_user, auth_headers):
    # address omitted -> schema validation (422)
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": "warehouse", "city": "metropolis"},
    )
    assert response.status_code == 422


async def test_create_location_forbidden_client(client, client_user, auth_headers):
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(client_user),
        json={"name": "warehouse", "city": "metropolis", "address": "123 st"},
    )
    assert response.status_code == 403


async def test_create_location_forbidden_employee(client, employee_user, auth_headers):
    # employees can list but must not be able to create
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(employee_user),
        json={"name": "warehouse", "city": "metropolis", "address": "123 st"},
    )
    assert response.status_code == 403


async def test_create_location_duplicate_name(client, admin_user, auth_headers):
    await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": "warehouse", "city": "gotham", "address": "elsewhere"},
    )
    assert response.status_code == 409


async def test_create_location_missing_name(client, admin_user, auth_headers):
    # name omitted -> schema validation (422)
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"city": "metropolis", "address": "123 st"},
    )
    assert response.status_code == 422


async def test_create_location_missing_city(client, admin_user, auth_headers):
    # city omitted -> schema validation (422)
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": "warehouse", "address": "123 st"},
    )
    assert response.status_code == 422


async def test_create_location_blank_name(client, admin_user, auth_headers):
    # whitespace-only name passes schema min_length but fails service validation (400)
    response = await client.post(
        "/inventory/locations",
        headers=auth_headers(admin_user),
        json={"name": "   ", "city": "metropolis", "address": "123 st"},
    )
    assert response.status_code == 400


# GET /inventory/locations/{id}


async def test_get_location(client, admin_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.get(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == location_id
    assert body["name"] == "warehouse"


async def test_get_location_not_found(client, admin_user, auth_headers):
    response = await client.get(
        f"/inventory/locations/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


async def test_get_location_employee_allowed(client, admin_user, employee_user, auth_headers):
    # employees have location:view
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.get(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(employee_user),
    )
    assert response.status_code == 200


async def test_get_location_forbidden(client, admin_user, client_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.get(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403


# PATCH /inventory/locations/{id}


async def test_update_location(client, admin_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.patch(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(admin_user),
        json={"city": "gotham", "address": "5 New Rd"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == location_id
    assert body["name"] == "warehouse"  # unchanged
    assert body["city"] == "gotham"
    assert body["address"] == "5 New Rd"


async def test_update_location_no_fields(client, admin_user, auth_headers):
    # empty payload -> service rejects with 400 (no parameters)
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.patch(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(admin_user),
        json={},
    )
    assert response.status_code == 400


async def test_update_location_duplicate_name(client, admin_user, auth_headers):
    await _create_location(client, admin_user, auth_headers, "warehouse")
    other_id = await _create_location(client, admin_user, auth_headers, "depot")

    response = await client.patch(
        f"/inventory/locations/{other_id}",
        headers=auth_headers(admin_user),
        json={"name": "warehouse"},
    )
    assert response.status_code == 409


async def test_update_location_not_found(client, admin_user, auth_headers):
    response = await client.patch(
        f"/inventory/locations/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
        json={"city": "gotham"},
    )
    assert response.status_code == 404


async def test_update_location_forbidden_employee(client, admin_user, employee_user, auth_headers):
    # employees can view but not update
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.patch(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(employee_user),
        json={"city": "gotham"},
    )
    assert response.status_code == 403


# DELETE /inventory/locations/{id}


async def test_delete_location(client, admin_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.delete(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 204

    # confirm it is gone
    follow_up = await client.get(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(admin_user),
    )
    assert follow_up.status_code == 404


async def test_delete_location_not_found(client, admin_user, auth_headers):
    response = await client.delete(
        f"/inventory/locations/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


async def test_delete_location_with_stock(client, admin_user, make_stock, auth_headers):
    # a location that still holds stock cannot be deleted
    stock = await make_stock(admin_user, quantity=10)

    response = await client.delete(
        f"/inventory/locations/{stock['location_id']}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 409


async def test_delete_location_forbidden_employee(client, admin_user, employee_user, auth_headers):
    location_id = await _create_location(client, admin_user, auth_headers, "warehouse")

    response = await client.delete(
        f"/inventory/locations/{location_id}",
        headers=auth_headers(employee_user),
    )
    assert response.status_code == 403
