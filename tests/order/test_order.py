import uuid

from app.orders.models.order import Order

# GET /orders/me


async def test_list_my_orders_returns_own_orders(
    client, employee_user, auth_headers, make_order
):
    first = await make_order(employee_user)
    second = await make_order(employee_user)

    response = await client.get(
        "/orders/me",
        headers=auth_headers(employee_user),
    )

    assert response.status_code == 200
    body = response.json()
    returned_ids = {o["id"] for o in body}
    assert returned_ids == {first, second}
    assert all(o["user_id"] == str(employee_user.id) for o in body)


async def test_list_my_orders_excludes_other_users_orders(
    client, employee_user, admin_user, auth_headers, make_order
):
    # an order owned by the employee must not appear for the admin
    employee_order = await make_order(employee_user)

    response = await client.get(
        "/orders/me",
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200
    returned_ids = {o["id"] for o in response.json()}
    assert employee_order not in returned_ids


async def test_list_my_orders_allowed_without_order_permission(
    client, client_user, auth_headers
):
    
    response = await client.get(
        "/orders/me",
        headers=auth_headers(client_user),
    )

    assert response.status_code == 200
    assert response.json() == []


async def test_list_my_orders_unauthenticated(client):
    response = await client.get("/orders/me")

    assert response.status_code == 401


# POST /orders

async def test_create_order(client, auth_headers, employee_user):
    response = await client.post(
        "orders/",
        headers=auth_headers(employee_user)
    )
    
    assert response.status_code == 201 


async def test_create_order_forbidden(client, auth_headers, client_user): 
    response = await client.post(
        "orders/",
        headers=auth_headers(client_user)
    )
    
    assert response.status_code == 403


async def test_add_item_to_order(
    client, employee_user, auth_headers, make_order, make_product
):
    order_id = await make_order(employee_user)
    product_id = await make_product(employee_user)

    response = await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == order_id
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["product_id"] == product_id
    assert item["quantity"] == 3


async def test_add_item_to_order_forbidden(
    client, client_user, employee_user, auth_headers, make_order, make_product
):
    order_id = await make_order(employee_user)
    product_id = await make_product(employee_user)

    response = await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(client_user),
        json={"product_id": product_id, "quantity": 3},
    )

    assert response.status_code == 403


async def test_add_item_to_order_product_not_found(
    client, employee_user, auth_headers, make_order
):
    order_id = await make_order(employee_user)

    response = await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": str(uuid.uuid4()), "quantity": 3},
    )

    assert response.status_code == 404


async def test_remove_item_from_order(
    client, employee_user, auth_headers, make_order, make_product
):
    order_id = await make_order(employee_user)
    product_id = await make_product(employee_user)

    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.delete(
        f"/orders/{order_id}/items/{product_id}",
        headers=auth_headers(employee_user),
    )

    assert response.status_code == 200
    assert all(i["product_id"] != product_id for i in response.json()["items"])


async def test_remove_item_from_order_forbidden(
    client, employee_user, client_user, auth_headers, make_order, make_product
):
    order_id = await make_order(employee_user)
    product_id = await make_product(employee_user)

    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.delete(
        f"/orders/{order_id}/items/{product_id}",
        headers=auth_headers(client_user),
    )

    assert response.status_code == 403


# GET /orders/code/{code}


async def _order_code(db_session, order_id: str) -> str:
    order = await db_session.get(Order, uuid.UUID(order_id))
    return order.code


async def test_get_order_by_code_returns_order(
    client, db_session, employee_user, make_order
):
    order_id = await make_order(employee_user)
    code = await _order_code(db_session, order_id)

    response = await client.get(f"/orders/code/{code}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id


async def test_get_order_by_code_normalizes_input(
    client, db_session, employee_user, make_order
):
    order_id = await make_order(employee_user)
    code = await _order_code(db_session, order_id)

    messy = code.replace("-", "").lower()
    response = await client.get(f"/orders/code/{messy}")

    assert response.status_code == 200
    assert response.json()["id"] == order_id


async def test_get_order_by_code_not_found(client):
    response = await client.get("/orders/code/ZZZZ-ZZZZ")

    assert response.status_code == 404


async def test_get_order_by_code_malformed(client):
    response = await client.get("/orders/code/abc")

    assert response.status_code == 404