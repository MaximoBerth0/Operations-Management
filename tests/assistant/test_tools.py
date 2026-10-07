import uuid

import pytest
from app.assistant.tools.base import ToolContext
from app.assistant.tools.registry import ALL_TOOLS, run_tool, tools_for
from app.inventory.repositories.category_repo import CategoryRepository
from app.inventory.repositories.location_repo import LocationRepository
from app.inventory.repositories.product_repo import ProductRepository
from app.inventory.repositories.reservation_repo import ReservationRepository
from app.inventory.repositories.stock_repo import StockRepository
from app.inventory.service import InventoryService
from app.rbac.repositories.permission_repo import PermissionRepository
from app.rbac.repositories.role_repo import RoleRepository
from app.rbac.service import RBACService

ALL_PERMISSIONS = {tool.permission for tool in ALL_TOOLS.values()}


@pytest.fixture
def make_ctx(db_session):
    def _make(user_id: uuid.UUID, location_id: uuid.UUID) -> ToolContext:
        service = InventoryService(
            stock_repo=StockRepository(db_session),
            product_repo=ProductRepository(db_session),
            category_repo=CategoryRepository(db_session),
            location_repo=LocationRepository(db_session),
            reservation_repo=ReservationRepository(db_session),
        )
        return ToolContext(inventory_service=service, user_id=user_id, location_id=location_id)

    return _make


# registry, no db

def test_tools_for_filters_by_permission():
    assert {t.name for t in tools_for({"stock:view"})} == {
        "get_replenishment_suggestions",
        "get_stock_levels",
        "list_stock_movements",
    }
    assert [t.name for t in tools_for({"location:list"})] == ["list_locations"]
    assert tools_for(set()) == []


def test_every_tool_has_a_json_schema():
    for tool in ALL_TOOLS.values():
        definition = tool.definition()
        assert definition["name"] == tool.name
        assert definition["input_schema"]["type"] == "object"


# run_tool

async def test_unknown_tool_is_an_error_result(make_ctx):
    result = await run_tool("drop_tables", {}, make_ctx(uuid.uuid4(), uuid.uuid4()), ALL_PERMISSIONS)

    assert result.is_error
    assert result.content["error_code"] == "TOOL_NOT_AVAILABLE"


async def test_permission_rechecked_on_execution(make_ctx):
    result = await run_tool(
        "list_locations", {}, make_ctx(uuid.uuid4(), uuid.uuid4()), {"stock:view"}
    )

    assert result.is_error
    assert result.content["error_code"] == "TOOL_NOT_AVAILABLE"


async def test_invalid_input_is_an_error_result(make_ctx):
    result = await run_tool(
        "get_replenishment_suggestions",
        {"horizon_days": 99},
        make_ctx(uuid.uuid4(), uuid.uuid4()),
        ALL_PERMISSIONS,
    )

    assert result.is_error
    assert result.content["error_code"] == "INVALID_TOOL_INPUT"
    assert result.content["detail"][0]["loc"] == ("horizon_days",)


async def test_service_error_is_an_error_result(make_ctx):
    result = await run_tool(
        "get_product",
        {"product_id": str(uuid.uuid4())},
        make_ctx(uuid.uuid4(), uuid.uuid4()),
        ALL_PERMISSIONS,
    )

    assert result.is_error
    assert result.content["error_code"] == "PRODUCT_NOT_FOUND"


async def test_replenishment_defaults_to_current_location(
    client, admin_user, auth_headers, make_stock, make_ctx
):
    stock = await make_stock(admin_user, quantity=100, reorder_point=5)
    response = await client.post(
        "/inventory/out",
        headers=auth_headers(admin_user, location_id=stock["location_id"]),
        json={"product_id": stock["product_id"], "quantity": 90},
    )
    assert response.status_code in (200, 201)

    result = await run_tool(
        "get_replenishment_suggestions",
        {},
        make_ctx(admin_user.id, uuid.UUID(stock["location_id"])),
        ALL_PERMISSIONS,
    )

    assert not result.is_error
    [item] = result.content["items"]
    assert item["stock_id"] == stock["stock_id"]
    assert item["product_name"] == "widget"
    assert item["location_name"] == "warehouse"
    assert item["suggested_quantity"] == 80


async def test_stock_levels_and_movements(
    client, admin_user, auth_headers, make_stock, make_ctx
):
    stock = await make_stock(admin_user, quantity=10, reorder_point=2)
    await client.post(
        "/inventory/out",
        headers=auth_headers(admin_user, location_id=stock["location_id"]),
        json={"product_id": stock["product_id"], "quantity": 4},
    )
    ctx = make_ctx(admin_user.id, uuid.UUID(stock["location_id"]))

    levels = await run_tool("get_stock_levels", {}, ctx, ALL_PERMISSIONS)
    movements = await run_tool(
        "list_stock_movements", {"stock_id": stock["stock_id"]}, ctx, ALL_PERMISSIONS
    )

    assert levels.content["items"][0]["quantity"] == 6
    assert levels.content["items"][0]["reserved_quantity"] == 0
    assert [m["movement_type"] for m in movements.content["items"]] == ["out"]


# permissions source

async def test_user_permissions(db_session, admin_user, plain_user):
    rbac = RBACService(
        role_repo=RoleRepository(db_session), permission_repo=PermissionRepository(db_session)
    )

    assert ALL_PERMISSIONS <= await rbac.get_user_permissions(admin_user.id)
    assert await rbac.get_user_permissions(plain_user.id) == set()
