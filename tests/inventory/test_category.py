"""
the category file test evaluates the following:

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

# POST inventory/categories 

async def test_create_category(client, admin_user, auth_headers):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": "category", "description": "cateogry_description"}
    )

    assert response.status_code == 201
    body = response.json() 
    assert body["name"] == "category"
    assert body["description"] == "cateogry_description"


# create category forbidden 403 

async def test_create_category_forbidden(client, client_user, auth_headers): 
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(client_user),
        json={"name": "category", "description": "cateogry_description"}
    )

    assert response.status_code == 403

# create category duplicate name 409 conflict 
    
async def test_create_category_duplicate_name(client, admin_user, auth_headers):
    # create the category once
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201

    # creating another category with the same name conflicts
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": "category", "description": "another_description"},
    )
    assert response.status_code == 409


# DELETE inventory/categories/{id}


async def test_delete_category(client, admin_user, auth_headers):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.delete(
        f"/inventory/categories/{category_id}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 204

# test delete category forbidden 403

async def test_delete_category_forbidden(client, admin_user, client_user, auth_headers):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(admin_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.delete(
        f"/inventory/categories/{category_id}",
        headers=auth_headers(client_user),
    )
    assert response.status_code == 403

# test delete category not found 404

async def test_delete_category_not_found(client, admin_user, auth_headers):
    response = await client.delete(
        f"/inventory/categories/{uuid.uuid4()}",
        headers=auth_headers(admin_user),
    )
    assert response.status_code == 404


# POST inventory/categories/{category_id}/products

async def test_add_product_to_cateogory(client, employee_user, auth_headers):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(employee_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(employee_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 201
    product_id = response.json()["id"]

    response = await client.post(
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(employee_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 200


async def test_add_product_to_category_forbidden(
    client, employee_user, client_user, auth_headers
):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(employee_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(employee_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 201
    product_id = response.json()["id"]

    response = await client.post(
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(client_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 403


# DELETE inventory/categories/{category_id}/products


async def test_remove_product_from_category(client, employee_user, auth_headers):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(employee_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(employee_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 201
    product_id = response.json()["id"]

    response = await client.post(
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(employee_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 200

    response = await client.request(
        "DELETE",
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(employee_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 204


async def test_remove_product_from_category_forbidden(
    client, employee_user, client_user, auth_headers
):
    response = await client.post(
        "/inventory/categories",
        headers=auth_headers(employee_user),
        json={"name": "category", "description": "cateogry_description"},
    )
    assert response.status_code == 201
    category_id = response.json()["id"]

    response = await client.post(
        "/inventory/products",
        headers=auth_headers(employee_user),
        json={"name": "widget", "sku": "SKU-1", "category_id": category_id},
    )
    assert response.status_code == 201
    product_id = response.json()["id"]

    response = await client.post(
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(employee_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 200

    response = await client.request(
        "DELETE",
        f"/inventory/categories/{category_id}/products",
        headers=auth_headers(client_user),
        json={"product_id": product_id},
    )
    assert response.status_code == 403