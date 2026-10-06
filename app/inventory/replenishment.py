"""Pure restock math: no DB, no I/O. The service gathers the numbers and calls evaluate()."""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class StockSnapshot:
    quantity: int
    reserved_quantity: int
    reorder_point: int

    @property
    def available(self) -> int:
        return self.quantity - self.reserved_quantity


@dataclass(frozen=True)
class ReplenishmentPolicy:
    window_days: int = 30   # history used to estimate consumption
    horizon_days: int = 7   # restock if stock runs out within this many days
    target_days: int = 30   # after restocking, cover this many days

    def __post_init__(self) -> None:
        if min(self.window_days, self.horizon_days, self.target_days) <= 0:
            raise ValueError("policy days must be positive")
        if self.target_days < self.horizon_days:
            raise ValueError("target_days must be >= horizon_days")


@dataclass(frozen=True)
class ReplenishmentSuggestion:
    available: int
    daily_consumption: float
    days_of_coverage: float | None  # None when there is no consumption
    needs_restock: bool
    suggested_quantity: int


def daily_consumption(consumed: int, window_days: int) -> float:
    if window_days <= 0:
        raise ValueError("window_days must be positive")
    return max(consumed, 0) / window_days


def days_of_coverage(available: int, daily: float) -> float | None:
    if daily <= 0:
        return None
    return max(available, 0) / daily


def evaluate(
    snapshot: StockSnapshot,
    consumed: int,
    policy: ReplenishmentPolicy = ReplenishmentPolicy(),
) -> ReplenishmentSuggestion:
    available = snapshot.available
    daily = daily_consumption(consumed, policy.window_days)
    coverage = days_of_coverage(available, daily)

    below_reorder_point = snapshot.reorder_point > 0 and available <= snapshot.reorder_point
    runs_out_soon = coverage is not None and coverage <= policy.horizon_days
    needs_restock = below_reorder_point or runs_out_soon

    suggested = 0
    if needs_restock:
        # cover target_days of demand and always end above the reorder point
        target_level = max(math.ceil(daily * policy.target_days), snapshot.reorder_point + 1)
        suggested = max(target_level - available, 0)

    return ReplenishmentSuggestion(
        available=available,
        daily_consumption=daily,
        days_of_coverage=coverage,
        needs_restock=needs_restock,
        suggested_quantity=suggested,
    )
