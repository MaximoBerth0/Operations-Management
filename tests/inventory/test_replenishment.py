import pytest
from app.inventory.replenishment import (
    ReplenishmentPolicy,
    StockSnapshot,
    daily_consumption,
    days_of_coverage,
    evaluate,
)


def _snap(quantity: int, reserved: int = 0, reorder_point: int = 0) -> StockSnapshot:
    return StockSnapshot(quantity=quantity, reserved_quantity=reserved, reorder_point=reorder_point)


# examples from app/assistant/design.md

def test_runs_out_within_horizon():
    result = evaluate(_snap(15), consumed=90)  # 3/day

    assert result.daily_consumption == 3
    assert result.days_of_coverage == 5
    assert result.needs_restock
    assert result.suggested_quantity == 75


def test_plenty_of_coverage_needs_nothing():
    result = evaluate(_snap(100), consumed=30)  # 1/day

    assert result.days_of_coverage == 100
    assert not result.needs_restock
    assert result.suggested_quantity == 0


def test_no_history_below_reorder_point_ends_above_it():
    result = evaluate(_snap(4, reorder_point=5), consumed=0)

    assert result.days_of_coverage is None
    assert result.needs_restock
    assert result.suggested_quantity == 2


def test_over_reserved_stock():
    result = evaluate(_snap(2, reserved=5), consumed=60)  # 2/day, -3 available

    assert result.available == -3
    assert result.days_of_coverage == 0
    assert result.suggested_quantity == 63


# edges

def test_no_history_and_no_reorder_point_never_restocks():
    result = evaluate(_snap(0), consumed=0)

    assert not result.needs_restock
    assert result.suggested_quantity == 0


def test_coverage_equal_to_horizon_restocks():
    result = evaluate(_snap(7), consumed=30)  # 1/day, exactly 7 days

    assert result.needs_restock


def test_reserved_units_are_not_available():
    result = evaluate(_snap(20, reserved=15, reorder_point=5), consumed=0)

    assert result.available == 5
    assert result.needs_restock
    assert result.suggested_quantity == 1


def test_target_level_rounds_up():
    result = evaluate(_snap(0), consumed=10)  # 1/3 per day, 10 over 30 days

    assert result.suggested_quantity == 10
    result = evaluate(_snap(0), consumed=11)
    assert result.suggested_quantity == 11


def test_custom_policy():
    policy = ReplenishmentPolicy(window_days=10, horizon_days=3, target_days=14)
    result = evaluate(_snap(5), consumed=20, policy=policy)  # 2/day, 2.5 days

    assert result.needs_restock
    assert result.suggested_quantity == 28 - 5


def test_negative_consumption_counts_as_zero():
    assert daily_consumption(-10, 30) == 0


def test_coverage_none_without_consumption():
    assert days_of_coverage(10, 0) is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_days": 0},
        {"horizon_days": -1},
        {"target_days": 0},
        {"horizon_days": 10, "target_days": 5},
    ],
)
def test_invalid_policy(kwargs):
    with pytest.raises(ValueError):
        ReplenishmentPolicy(**kwargs)


def test_invalid_window_for_daily_consumption():
    with pytest.raises(ValueError):
        daily_consumption(10, 0)
