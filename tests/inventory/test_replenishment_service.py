from datetime import datetime, timedelta, timezone

import pytest
from app.inventory.exceptions import InvalidReplenishmentPolicy
from app.inventory.models.enums import StockMovementType
from app.inventory.models.stock import StockMovement
from app.inventory.repositories.category_repo import CategoryRepository
from app.inventory.repositories.location_repo import LocationRepository
from app.inventory.repositories.product_repo import ProductRepository
from app.inventory.repositories.reservation_repo import ReservationRepository
from app.inventory.repositories.stock_repo import StockRepository
from app.inventory.service import InventoryService


@pytest.fixture
def service(db_session) -> InventoryService:
    return InventoryService(
        stock_repo=StockRepository(db_session),
        product_repo=ProductRepository(db_session),
        category_repo=CategoryRepository(db_session),
        location_repo=LocationRepository(db_session),
        reservation_repo=ReservationRepository(db_session),
    )


async def _out(client, auth_headers, user, stock, quantity):
    response = await client.post(
        "/inventory/out",
        headers=auth_headers(user, location_id=stock["location_id"]),
        json={"product_id": stock["product_id"], "quantity": quantity},
    )
    assert response.status_code in (200, 201), response.text


async def _old_out(db_session, user, stock, quantity, days_ago):
    db_session.add(
        StockMovement(
            stock_id=stock["stock_id"],
            movement_type=StockMovementType.OUT,
            quantity=quantity,
            previous_quantity=0,
            new_quantity=0,
            created_by=user.id,
            created_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        )
    )
    await db_session.commit()


async def test_suggests_restock_from_consumption(
    client, admin_user, auth_headers, make_stock, service
):
    stock = await make_stock(admin_user, quantity=100, reorder_point=5)
    await _out(client, auth_headers, admin_user, stock, 90)  # 3/day over 30 days

    rows = await service.get_replenishment_suggestions(location_id=stock["location_id"])

    assert len(rows) == 1
    row = rows[0]
    assert str(row.stock.id) == stock["stock_id"]
    assert row.stock.product.name == "widget"
    assert row.suggestion.available == 10
    assert row.suggestion.daily_consumption == 3
    assert row.suggestion.suggested_quantity == 80


async def test_movements_outside_window_are_ignored(
    client, admin_user, auth_headers, make_stock, service, db_session
):
    stock = await make_stock(admin_user, quantity=100, reorder_point=0)
    await _out(client, auth_headers, admin_user, stock, 30)  # 1/day, 70 days left
    await _old_out(db_session, admin_user, stock, 900, days_ago=40)

    rows = await service.get_replenishment_suggestions(
        location_id=stock["location_id"], only_needed=False
    )

    assert rows[0].suggestion.daily_consumption == 1
    assert not rows[0].suggestion.needs_restock


async def test_only_needed_filters_healthy_rows(
    admin_user, make_stock, make_product, make_category, service
):
    healthy = await make_stock(admin_user, quantity=100, reorder_point=0)
    category_id = await make_category(admin_user, name="other")
    product_id = await make_product(admin_user, sku="SKU-2", category_id=category_id)
    await make_stock(
        admin_user, product_id=product_id, location_id=healthy["location_id"],
        quantity=3, reorder_point=5,
    )

    needed = await service.get_replenishment_suggestions(location_id=healthy["location_id"])
    everything = await service.get_replenishment_suggestions(
        location_id=healthy["location_id"], only_needed=False
    )

    assert [str(r.stock.product_id) for r in needed] == [product_id]
    assert len(everything) == 2


async def test_most_urgent_first(
    client, admin_user, auth_headers, make_stock, make_product, make_category, service
):
    slow = await make_stock(admin_user, quantity=10, reorder_point=0)
    location_id = slow["location_id"]
    category_id = await make_category(admin_user, name="other")
    fast_product = await make_product(admin_user, sku="SKU-2", category_id=category_id)
    fast = await make_stock(
        admin_user, product_id=fast_product, location_id=location_id, quantity=10, reorder_point=0
    )
    no_history_product = await make_product(admin_user, sku="SKU-3", category_id=category_id)
    await make_stock(
        admin_user, product_id=no_history_product, location_id=location_id,
        quantity=3, reorder_point=5,
    )
    await _out(client, auth_headers, admin_user, slow, 5)  # 5 left at 1/6 per day: 30 days
    await _out(client, auth_headers, admin_user, fast, 8)  # 2 left at 8/30 per day: 7.5 days

    rows = await service.get_replenishment_suggestions(location_id=location_id, horizon_days=30)

    assert [str(r.stock.product_id) for r in rows] == [
        fast_product, slow["product_id"], no_history_product,
    ]


async def test_location_filter(
    client, admin_user, auth_headers, make_stock, make_location, service
):
    here = await make_stock(admin_user, quantity=10, reorder_point=0)
    other_location = await make_location(admin_user, name="other")
    other = await make_stock(
        admin_user, product_id=here["product_id"], location_id=other_location,
        quantity=10, reorder_point=0,
    )
    await _out(client, auth_headers, admin_user, here, 9)
    await _out(client, auth_headers, admin_user, other, 9)

    rows = await service.get_replenishment_suggestions(location_id=here["location_id"])
    everywhere = await service.get_replenishment_suggestions()

    assert [str(r.stock.id) for r in rows] == [here["stock_id"]]
    assert len(everywhere) == 2


async def test_completed_order_counts_as_consumption(
    client, admin_user, auth_headers, make_stock, make_order_item, service, db_session
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=0)
    location_id = stock["location_id"]
    item = await make_order_item(admin_user, product_id=stock["product_id"], quantity=6)
    headers = auth_headers(admin_user, location_id=location_id)

    response = await client.patch(f"/orders/{item['order_id']}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    # shared session: drop the cached OrderItem.reservation (see test_reservation.py)
    db_session.expire_all()
    response = await client.patch(f"/orders/{item['order_id']}/complete", headers=headers)
    assert response.status_code == 200, response.text

    rows = await service.get_replenishment_suggestions(location_id=location_id, only_needed=False)

    assert rows[0].suggestion.daily_consumption == pytest.approx(6 / 30)


async def test_invalid_horizon_raises(service):
    with pytest.raises(InvalidReplenishmentPolicy):
        await service.get_replenishment_suggestions(horizon_days=40)
