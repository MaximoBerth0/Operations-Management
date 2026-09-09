"""
the stock file test evaluates the following:

- Happy path      - normal expected behavior
- Validation      - bad input, missing fields
- Auth/Permission - unauthorized, forbidden
- Edge cases      - duplicates, not found, etc.

Initializing stock needs both a product and a location, so these tests lean on
the shared entity builders from integration/conftest.py instead of redefining
helpers here:
- `make_product`  : create a product (auto-creates its category) -> product id
- `make_location` : create a location -> location id

Other fixtures from integration/conftest.py:
- `admin_user`    : user with the admin role (all permissions)
- `employee_user` : user with the employee role (no `stock:create`)
- `client_user`   : user with the client role (no permissions)
- `auth_headers`  : builds the Authorization header for a user; pass
                    `location_id=` to also attach the X-Location-Id header
"""

import uuid

# POST /inventory/new  (initialize stock)


async def test_create_stock(client, admin_user, auth_headers, make_product, make_location):
    product_id = await make_product(admin_user)
    location_id = await make_location(admin_user)

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user, location_id=location_id),
        json={
            "product_id": product_id,
            "quantity": 10,
            "reorder_point": 2,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["location_id"] == location_id
    assert body["product_id"] == product_id
    assert body["quantity"] == 10
    assert body["reorder_point"] == 2


async def test_create_stock_reorder_point_capped(
    client, admin_user, auth_headers, make_product, make_location
):
    # service caps reorder_point at the initial quantity
    product_id = await make_product(admin_user)
    location_id = await make_location(admin_user)

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user, location_id=location_id),
        json={
            "product_id": product_id,
            "quantity": 5,
            "reorder_point": 99,
        },
    )
    assert response.status_code == 201
    assert response.json()["reorder_point"] == 5


async def test_create_stock_duplicate(
    client, admin_user, auth_headers, make_product, make_location
):
    # initializing stock twice for the same (product, location) is rejected;
    # the second call should use stock-in instead
    product_id = await make_product(admin_user)
    location_id = await make_location(admin_user)
    headers = auth_headers(admin_user, location_id=location_id)
    payload = {"product_id": product_id, "quantity": 10, "reorder_point": 2}

    first = await client.post("/inventory/new", headers=headers, json=payload)
    assert first.status_code == 201

    second = await client.post("/inventory/new", headers=headers, json=payload)
    assert second.status_code == 409


async def test_create_stock_forbidden_client(client, client_user, auth_headers):
    response = await client.post(
        "/inventory/new",
        headers=auth_headers(client_user),
        json={"product_id": 1, "quantity": 10, "reorder_point": 2},
    )
    assert response.status_code == 403


async def test_create_stock_forbidden_employee(client, employee_user, auth_headers):
    # employees can move stock (in/out/adjust) but cannot initialize it
    response = await client.post(
        "/inventory/new",
        headers=auth_headers(employee_user),
        json={"product_id": 1, "quantity": 10, "reorder_point": 2},
    )
    assert response.status_code == 403


async def test_create_stock_missing_field(
    client, admin_user, auth_headers, make_location
):
    # quantity omitted -> schema validation (422)
    location_id = await make_location(admin_user)

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user, location_id=location_id),
        json={"product_id": 1, "reorder_point": 2},
    )
    assert response.status_code == 422


async def test_create_stock_invalid_location(client, admin_user, auth_headers):

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user, location_id=uuid.uuid4()),
        json={"product_id": str(uuid.uuid4()), "quantity": 10, "reorder_point": 2},
    )
    assert response.status_code == 404


async def test_create_stock_missing_location_header(
    client, admin_user, auth_headers, make_product
):
    # no X-Location-Id header -> get_current_location rejects with 400
    product_id = await make_product(admin_user)

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user),
        json={"product_id": product_id, "quantity": 10, "reorder_point": 2},
    )
    assert response.status_code == 400


async def test_create_stock_zero_quantity(
    client, admin_user, auth_headers, make_product, make_location
):
    product_id = await make_product(admin_user)
    location_id = await make_location(admin_user)

    response = await client.post(
        "/inventory/new",
        headers=auth_headers(admin_user, location_id=location_id),
        json={
            "product_id": product_id,
            "quantity": 0,
            "reorder_point": 0,
        },
    )
    assert response.status_code == 400


# POST inventory/in

async def test_add_stock(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/in",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["new_quantity"] == 40


async def test_add_stock_forbidden(client, client_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/in",
        headers=auth_headers(client_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 30,
        },
    )

    assert response.status_code == 403


async def test_add_stock_invalid_quantity(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/in",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": -20,
        },
    )

    assert response.status_code == 400



# POST inventory/out


async def test_remove_stock(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=120)

    response = await client.post(
        "/inventory/out",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 30,
        },
    )

    assert response.status_code == 200
    assert response.json()["new_quantity"] == 90


async def test_remove_stock_forbidden(client, client_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=120)

    response = await client.post(
        "/inventory/out",
        headers=auth_headers(client_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 30,
        },
    )

    assert response.status_code == 403


async def test_remove_stock_invalid_quantity(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=120)

    response = await client.post(
        "/inventory/out",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": -50,
        },
    )

    assert response.status_code == 400


async def test_adjust_stock(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/adjust",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 50
        },
    )

    assert response.status_code == 200
    assert response.json()["new_quantity"] == 50


async def test_adjust_stock_forbidden(client, client_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/adjust",
        headers=auth_headers(client_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": 50
        },
    )

    assert response.status_code == 403


async def test_adjust_stock_invalid_quantity(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.post(
        "/inventory/adjust",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        json={
            "product_id": stock["product_id"],
            "quantity": -10
        },
    )

    assert response.status_code == 400

# GET /inventory/movements


async def test_list_movements(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)
    headers = auth_headers(employee_user, location_id=stock["location_id"])
    payload = {"product_id": stock["product_id"]}

    # three movements: in, out, adjust (initialize_stock does not log a movement)
    await client.post("/inventory/in", headers=headers, json={**payload, "quantity": 5})
    await client.post("/inventory/out", headers=headers, json={**payload, "quantity": 3})
    await client.post("/inventory/adjust", headers=headers, json={**payload, "quantity": 20})

    response = await client.get(
        "/inventory/movements",
        headers=headers,
        params={"stock_id": stock["stock_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 3
    assert all(item["stock_id"] == stock["stock_id"] for item in body["items"])
    assert {item["movement_type"] for item in body["items"]} == {"in", "out", "adjust"}


async def test_list_movements_empty(client, employee_user, admin_user, make_stock, auth_headers):
    # a freshly initialized stock has no recorded movements
    stock = await make_stock(admin_user, quantity=10)

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        params={"stock_id": stock["stock_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["items"] == []


async def test_list_movements_respects_limit(client, employee_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)
    headers = auth_headers(employee_user, location_id=stock["location_id"])
    payload = {"product_id": stock["product_id"]}
    for _ in range(3):
        await client.post("/inventory/in", headers=headers, json={**payload, "quantity": 1})

    response = await client.get(
        "/inventory/movements",
        headers=headers,
        params={"stock_id": stock["stock_id"], "limit": 2},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) == 2


async def test_list_movements_other_location(
    client, employee_user, admin_user, make_stock, make_location, auth_headers
):
    # the current branch may only read its own stock's history: asking for a
    # stock row that lives in another location is hidden behind a 404
    stock = await make_stock(admin_user, quantity=10)
    other_location_id = await make_location(admin_user, name="other-branch")

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(employee_user, location_id=other_location_id),
        params={"stock_id": stock["stock_id"]},
    )

    assert response.status_code == 404


async def test_list_movements_forbidden(client, client_user, admin_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(client_user, location_id=stock["location_id"]),
        params={"stock_id": stock["stock_id"]},
    )

    assert response.status_code == 403


async def test_list_movements_missing_stock_id(
    client, employee_user, admin_user, make_location, auth_headers
):
    # stock_id is a required query param -> schema validation (422)
    location_id = await make_location(admin_user)

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 422


async def test_list_movements_invalid_stock_id(
    client, employee_user, admin_user, make_location, auth_headers
):
    # stock_id must be > 0 -> schema validation (422)
    location_id = await make_location(admin_user)

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(employee_user, location_id=location_id),
        params={"stock_id": 0},
    )

    assert response.status_code == 422


async def test_list_movements_stock_not_found(
    client, employee_user, admin_user, make_location, auth_headers
):
    location_id = await make_location(admin_user)

    response = await client.get(
        "/inventory/movements",
        headers=auth_headers(employee_user, location_id=location_id),
        params={"stock_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404

# GET inventory/stock


async def test_get_stock_level(client, admin_user, employee_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.get(
        "/inventory/stock",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
        params={"product_id": stock["product_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == stock["stock_id"]
    assert item["product_id"] == stock["product_id"]
    assert item["location_id"] == stock["location_id"]
    assert item["quantity"] == 10



async def test_get_stock_level_forbidden(client, admin_user, client_user, make_stock, auth_headers):
    stock = await make_stock(admin_user, quantity=10)

    response = await client.get(
        "/inventory/stock",
        headers=auth_headers(client_user, location_id=stock["location_id"]),
        params={"product_id": stock["product_id"]},
    )

    assert response.status_code == 403


async def test_get_stock_level_reorder_point(client, admin_user, make_stock, auth_headers):
    # get_stock_levels should report the current quantity along with the
    # reorder_point established when the stock was created
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)
    headers = auth_headers(admin_user, location_id=stock["location_id"])

    response = await client.post(
        "/inventory/out",
        headers=headers,
        json={
            "product_id": stock["product_id"],
            "quantity": 6,
        },
    )
    assert response.status_code == 200

    response = await client.get(
        "/inventory/stock",
        headers=headers,
        params={"product_id": stock["product_id"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == stock["stock_id"]
    assert item["quantity"] == 4  # current quantity after removal
    assert item["reorder_point"] == 5  # unchanged from creation
