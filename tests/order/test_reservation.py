from app.inventory.models.stock import InventoryStock


async def _read_stock(db_session, stock_id: int) -> InventoryStock:
    # the request mutates the stock row through the same session. populate_existing
    # forces a fresh SELECT (within this awaited call) that overwrites the cached instance
    return await db_session.get(
        InventoryStock, stock_id, populate_existing=True
    )


# PATCH orders/{id}/confirm

async def test_confirm_order(
    client, auth_headers, admin_user, employee_user, make_stock, make_order, db_session
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    # confirming reserves the stock: physical quantity is untouched
    # in reserved_quantity (available = 10 - 3 = 7).
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.quantity == 10
    assert row.reserved_quantity == 3


async def test_confirm_order_forbidden(
    client, auth_headers, admin_user, employee_user, client_user, make_stock, make_order
):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(client_user, location_id=location_id),
    )

    assert response.status_code == 403


async def test_confirm_order_insufficient_stock(
    client, auth_headers, admin_user, employee_user, make_stock, make_order, db_session
):
    # only 2 in stock, but the order asks for 5 > reserve raises InsufficientStock
    stock = await make_stock(admin_user, quantity=2)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 5},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 409

    row = await _read_stock(db_session, stock["stock_id"])
    assert row.quantity == 2
    assert row.reserved_quantity == 0


async def test_confirm_order_no_stock_at_location(
    client, auth_headers, admin_user, employee_user, make_stock, make_location, make_order
):
    # stock exists at one location, but we confirm against another that has none
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    other_location_id = await make_location(admin_user, name="depot", city="gotham")

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=other_location_id),
    )

    assert response.status_code == 404


# PATCH orders/{id}/complete

async def test_complete_order(
        client, auth_headers, admin_user, employee_user, make_stock, make_order, db_session
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    # confirm holds the 3 units in reserve.
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.quantity == 10
    assert row.reserved_quantity == 3

    # tests share one session with the request, so the OrderItem.reservation
    # relationship is still cached as None 
    # expire_all() also expires the user fixtures, and reading
    # user.id afterwards would lazy-load outside the async greenlet.
    headers = auth_headers(employee_user, location_id=location_id)
    db_session.expire_all()

    response = await client.patch(
        f"/orders/{order_id}/complete",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    # completing fulfills the reservation: the 3 reserved units leave physical
    # stock (10 -> 7) and the reservation hold is cleared.
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.quantity == 7
    assert row.reserved_quantity == 0


async def test_complete_order_forbidden(
        client, auth_headers, admin_user, employee_user, client_user, make_stock, make_order
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    response = await client.patch(
        f"/orders/{order_id}/complete",
        headers=auth_headers(client_user, location_id=location_id),
    )

    assert response.status_code == 403


async def test_complete_order_wrong_status(
        client, auth_headers, admin_user, employee_user, make_stock, make_order
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    # request fails because order should have 'CONFIRMED' status
    response = await client.patch(
        f"/orders/{order_id}/complete",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 409


# PATCH orders/{id}/cancel

async def test_cancel_order(
        client, auth_headers, admin_user, employee_user, make_stock, make_order, db_session
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    # confirm holds the 3 units in reserve.
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.reserved_quantity == 3

    # tests share one session with the request, so the OrderItem.reservation
    # relationship is still cached as None 
    # expire_all() also expires the user fixtures, and reading
    # user.id afterwards would lazy-load outside the async greenlet.
    headers = auth_headers(employee_user, location_id=location_id)
    db_session.expire_all()

    response = await client.patch(
        f"/orders/{order_id}/cancel",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # cancelling releases the reservation: the hold is dropped and the full 10
    # units are available again, with no physical stock consumed
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.quantity == 10
    assert row.reserved_quantity == 0


async def test_cancel_order_forbidden(
        client, auth_headers, admin_user, employee_user, client_user, make_stock, make_order
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"

    response = await client.patch(
        f"/orders/{order_id}/cancel",
        headers=auth_headers(client_user, location_id=location_id),
    )

    assert response.status_code == 403


async def test_cancel_order_wrong_status(
        client, auth_headers, admin_user, employee_user, make_stock, make_order
):
    # admin seeds infra (employee lacks location:create / stock:create):
    stock = await make_stock(admin_user, quantity=10)
    product_id = stock["product_id"]
    location_id = stock["location_id"]

    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": product_id, "quantity": 3},
    )

    response = await client.patch(
        f"/orders/{order_id}/cancel",
        headers=auth_headers(employee_user, location_id=location_id),
    )

    assert response.status_code == 409