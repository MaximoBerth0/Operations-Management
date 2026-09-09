"""
the product file test evaluates the following:

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


async def _create_category(client, admin_user, auth_headers, name, description="cat"):
    """helper: create a category and return its id"""
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": name, "description": description},
    )
    assert response.status_code == 201
    return response.json()["id"]

async def _create_product(client, admin_user, auth_headers, name, sku, category_id):
    """helper: create a product and return its id"""
    response = await client.post(
        "/inventory/products",
        headers=auth_headers(admin_user),
        json={"name": name, "sku": sku, "category_id": category_id},
    )
    assert response.status_code == 201
    return response.json()["id"]

# GET inventory/products/{id}


async def test_get_product(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.get(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    assert response.json()["id"] == product_id


async def test_get_product_forbidden(client, admin_user, client_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.get(
        f"/inventory/products/{product_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403

async def test_get_product_not_found(client, admin_user, auth_headers):
    response = await client.get(
        f"/inventory/products/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404

# GET inventory/products


async def test_list_products(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.get(
        "/inventory/products",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    ids = [product["id"] for product in response.json()]
    assert product_id in ids


async def test_list_products_forbidden(client, client_user, auth_headers):
    response = await client.get(
        "/inventory/products",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403

# POST inventory/products


async def test_create_product(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(admin_user),
        json={"name": "widget", "sku": "sku-1", "category_id": category_id},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "widget"
    assert body["sku"] == "SKU-1"  # normalized to upper-case
    assert body["is_active"] is True


async def test_create_product_forbidden(client, admin_user, client_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(client_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 403


async def test_create_product_duplicate_sku(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    await _create_product(client, admin_user, auth_headers, "widget", "SKU-1", category_id)

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(admin_user),
        json={"name": "gadget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 409


async def test_create_product_category_not_found(client, admin_user, auth_headers):
    response = await client.post(
        "/inventory/products",
        headers=auth_headers(admin_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404

# PATCH inventory/products/{id}


async def test_update_product(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.patch(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
        json={"name": "gadget", "sku": "sku-2"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "gadget"
    assert body["sku"] == "SKU-2"  # normalized to upper-case


async def test_update_product_forbidden(client, admin_user, client_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.patch(
        f"/inventory/products/{product_id}",
        headers=auth_headers(client_user),
        json={"name": "gadget"},
    )
    assert response.status_code == 403


async def test_update_product_not_found(client, admin_user, auth_headers):
    response = await client.patch(
        f"/inventory/products/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
        json={"name": "gadget"},
    )
    assert response.status_code == 404


async def test_update_product_no_parameters(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.patch(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
        json={},
    )
    assert response.status_code == 400


async def test_update_product_duplicate_sku(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    await _create_product(client, admin_user, auth_headers, "widget", "SKU-1", category_id)
    product_id = await _create_product(
        client, admin_user, auth_headers, "gadget", "SKU-2", category_id
    )

    response = await client.patch(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
        json={"sku": "SKU-1"},
    )
    assert response.status_code == 409

# DELETE /inventory/products/{id}  (deactivate)


async def test_deactivate_product(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.delete(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 204

    # product is now inactive
    response = await client.get(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False


async def test_deactivate_product_forbidden(client, admin_user, client_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.delete(
        f"/inventory/products/{product_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403


async def test_deactivate_product_not_found(client, admin_user, auth_headers):
    response = await client.delete(
        f"/inventory/products/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404

# POST /inventory/products/{id}/activate


async def test_activate_product(client, admin_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    # deactivate first so activation is observable
    response = await client.delete(
        f"/inventory/products/{product_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 204

    response = await client.post(
        f"/inventory/products/{product_id}/activate",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is True


async def test_activate_product_forbidden(client, admin_user, client_user, auth_headers):
    category_id = await _create_category(client, admin_user, auth_headers, "tools")
    product_id = await _create_product(
        client, admin_user, auth_headers, "widget", "SKU-1", category_id
    )

    response = await client.post(
        f"/inventory/products/{product_id}/activate",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403


async def test_activate_product_not_found(client, admin_user, auth_headers):
    response = await client.post(
        f"/inventory/products/{uuid.uuid4()}/activate",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


