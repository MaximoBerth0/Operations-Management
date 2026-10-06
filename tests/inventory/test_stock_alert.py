from contextlib import asynccontextmanager
from datetime import datetime, timezone

from app.inventory.models.stock import InventoryStock
from app.rbac.models.user_role import user_roles
from app.users.model import User
from app.users.repository import UserRepository
from app.worker.tasks import stock_alert


async def _read_stock(db_session, stock_id) -> InventoryStock:
    return await db_session.get(InventoryStock, stock_id, populate_existing=True)


async def _move(client, auth_headers, user, stock, path, quantity):
    response = await client.post(
        f"/inventory/{path}",
        headers=auth_headers(user, location_id=stock["location_id"]),
        json={"product_id": stock["product_id"], "quantity": quantity},
    )
    assert response.status_code in (200, 201), response.text
    return response


# detection on stock movements

async def test_out_crossing_reorder_point_alerts_once(
    client, admin_user, make_stock, auth_headers, db_session, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)

    await _move(client, auth_headers, admin_user, stock, "out", 2)
    assert low_stock_alerts == []

    await _move(client, auth_headers, admin_user, stock, "out", 3)
    assert [str(s) for s in low_stock_alerts] == [stock["stock_id"]]
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.low_stock_alerted_at is not None

    # still low: no second alert
    await _move(client, auth_headers, admin_user, stock, "out", 1)
    assert len(low_stock_alerts) == 1


async def test_recovery_rearms_alert(
    client, admin_user, make_stock, auth_headers, db_session, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)

    await _move(client, auth_headers, admin_user, stock, "out", 6)
    assert len(low_stock_alerts) == 1

    await _move(client, auth_headers, admin_user, stock, "in", 10)
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.low_stock_alerted_at is None

    await _move(client, auth_headers, admin_user, stock, "out", 10)
    assert len(low_stock_alerts) == 2


async def test_adjust_below_reorder_point_alerts(
    client, admin_user, make_stock, auth_headers, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)

    await _move(client, auth_headers, admin_user, stock, "adjust", 3)
    assert [str(s) for s in low_stock_alerts] == [stock["stock_id"]]


async def test_reorder_point_zero_never_alerts(
    client, admin_user, make_stock, auth_headers, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=0)

    await _move(client, auth_headers, admin_user, stock, "out", 10)
    assert low_stock_alerts == []


async def test_initialize_below_reorder_point_alerts(
    admin_user, make_stock, db_session, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=3, reorder_point=5)

    assert [str(s) for s in low_stock_alerts] == [stock["stock_id"]]
    row = await _read_stock(db_session, stock["stock_id"])
    assert row.low_stock_alerted_at is not None


# detection on reservations

async def test_confirm_order_reservation_alerts(
    client, admin_user, employee_user, make_stock, make_order, auth_headers, low_stock_alerts
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)
    order_id = await make_order(employee_user)
    await client.post(
        f"/orders/{order_id}/items",
        headers=auth_headers(employee_user),
        json={"product_id": stock["product_id"], "quantity": 6},
    )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
    )
    assert response.status_code == 200
    # quantity is untouched, but available (10 - 6) dropped below 5
    assert [str(s) for s in low_stock_alerts] == [stock["stock_id"]]


async def test_failed_confirm_does_not_alert(
    client,
    admin_user,
    employee_user,
    make_stock,
    make_category,
    make_product,
    make_order,
    auth_headers,
    low_stock_alerts,
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)
    category_id = await make_category(admin_user, name="spares")
    other_product = await make_product(
        admin_user, name="gadget", sku="SKU-2", category_id=category_id
    )
    other = await make_stock(
        admin_user,
        product_id=other_product,
        location_id=stock["location_id"],
        quantity=1,
        reorder_point=0,
    )
    order_id = await make_order(employee_user)
    # first item would cross the threshold, second fails for lack of stock
    for product_id, quantity in ((stock["product_id"], 6), (other["product_id"], 5)):
        await client.post(
            f"/orders/{order_id}/items",
            headers=auth_headers(employee_user),
            json={"product_id": product_id, "quantity": quantity},
        )

    response = await client.patch(
        f"/orders/{order_id}/confirm",
        headers=auth_headers(employee_user, location_id=stock["location_id"]),
    )
    assert response.status_code == 409
    assert low_stock_alerts == []


# recipients

async def test_recipients_are_active_users_with_permission(
    db_session, seeded, admin_user, employee_user
):
    disabled_admin = User(
        email="old-admin@test.com",
        username="old-admin",
        hashed_password="x",
        disabled_at=datetime.now(timezone.utc),
    )
    db_session.add(disabled_admin)
    await db_session.flush()
    await db_session.execute(
        user_roles.insert().values(
            user_id=disabled_admin.id, role_id=seeded["roles"]["admin"].id
        )
    )

    emails = await UserRepository(db_session).list_emails_with_permission("stock:alert")
    assert emails == [admin_user.email]


# worker job

def _patch_job(monkeypatch, db_session) -> list[dict]:
    @asynccontextmanager
    async def session_ctx():
        yield db_session

    deferred: list[dict] = []

    async def record(**kwargs):
        deferred.append(kwargs)

    monkeypatch.setattr(stock_alert, "get_script_session", session_ctx)
    monkeypatch.setattr(stock_alert.send_low_stock_email_job, "defer_async", record)
    return deferred


async def test_job_emails_each_recipient(
    client, admin_user, make_stock, auth_headers, db_session, monkeypatch
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)
    await _move(client, auth_headers, admin_user, stock, "out", 7)
    deferred = _patch_job(monkeypatch, db_session)

    await stock_alert.low_stock_alert_job.func(stock_id=stock["stock_id"])

    assert len(deferred) == 1
    assert deferred[0]["email"] == admin_user.email
    assert deferred[0]["sku"] == "SKU-1"
    assert deferred[0]["available"] == 3
    assert deferred[0]["reorder_point"] == 5


async def test_job_skips_recovered_stock(
    client, admin_user, make_stock, auth_headers, db_session, monkeypatch
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=5)
    await _move(client, auth_headers, admin_user, stock, "out", 7)
    await _move(client, auth_headers, admin_user, stock, "in", 10)
    deferred = _patch_job(monkeypatch, db_session)

    await stock_alert.low_stock_alert_job.func(stock_id=stock["stock_id"])

    assert deferred == []
