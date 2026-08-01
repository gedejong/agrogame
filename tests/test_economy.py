"""Tests for economic ledger (AGRO-109)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agrogame.game.economy import (
    CostEntry,
    EconomicLedger,
    PriceTable,
)


@pytest.fixture()
def prices() -> PriceTable:
    return PriceTable.load(Path("data/economy/prices.yaml"))


# ---------------------------------------------------------------------------
# PriceTable
# ---------------------------------------------------------------------------
class TestPriceTable:
    def test_load_prices(self, prices: PriceTable) -> None:
        assert "fertilizer_urea" in prices.input_costs
        assert "maize" in prices.crop_prices
        assert prices.crop_prices["maize"].base_credits_per_kg == pytest.approx(0.22)

    def test_seasonal_multiplier(self, prices: PriceTable) -> None:
        """Q3 maize price = 0.22 * 0.8 = 0.176."""
        p = prices.get_crop_price("maize", quarter=3)
        assert p == pytest.approx(0.22 * 0.8)

    def test_unknown_crop_returns_zero(self, prices: PriceTable) -> None:
        assert prices.get_crop_price("mango") == 0.0

    def test_all_crops_have_4_multipliers(self, prices: PriceTable) -> None:
        for key, cp in prices.crop_prices.items():
            assert len(cp.seasonal_multipliers) == 4, f"{key} missing multipliers"


# ---------------------------------------------------------------------------
# CostEntry
# ---------------------------------------------------------------------------
class TestCostEntry:
    def test_frozen(self) -> None:
        entry = CostEntry(
            day=10, category="fertilizer", description="urea 50kg", amount_credits=50
        )
        with pytest.raises(AttributeError):
            entry.day = 20  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EconomicLedger — cost tracking
# ---------------------------------------------------------------------------
class TestCostTracking:
    def test_record_cost(self) -> None:
        ledger = EconomicLedger()
        ledger.record_cost(5, "fertilizer", "urea 100kg/ha", 100)
        assert len(ledger.costs) == 1
        assert ledger.costs[0].amount_credits == 100
        assert ledger.season_costs == 100

    def test_multiple_costs_accumulate(self) -> None:
        ledger = EconomicLedger()
        ledger.record_cost(1, "seed", "maize seed", 200)
        ledger.record_cost(5, "fertilizer", "urea", 100)
        ledger.record_cost(30, "irrigation", "30mm", 60)
        assert ledger.season_costs == 360
        assert len(ledger.costs) == 3

    def test_zero_cost_ignored(self) -> None:
        ledger = EconomicLedger()
        ledger.record_cost(1, "seed", "free", 0)
        assert len(ledger.costs) == 0


# ---------------------------------------------------------------------------
# AC: profitable season increases credit balance
# ---------------------------------------------------------------------------
def test_profitable_season_increases_balance(prices: PriceTable) -> None:
    ledger = EconomicLedger(balance_credits=10000)
    ledger.record_cost(0, "seed", "maize", 200)
    ledger.record_cost(20, "fertilizer", "urea 100kg", 100)
    # 500 g/m2 grain * 10 = 5000 kg/ha * 0.22 * 0.8 (Q3) = 880 credits
    profit = ledger.settle_season(
        grain_g_m2=500.0, crop_key="maize", prices=prices, quarter=3
    )
    assert profit > 0
    assert ledger.balance_credits > 10000


# ---------------------------------------------------------------------------
# AC: over-spending produces negative profit
# ---------------------------------------------------------------------------
def test_overspending_produces_negative_profit(prices: PriceTable) -> None:
    ledger = EconomicLedger(balance_credits=10000)
    # Spend a lot
    ledger.record_cost(0, "seed", "maize", 200)
    ledger.record_cost(1, "equipment", "tractor", 500)
    for d in range(50):
        ledger.record_cost(d, "irrigation", f"day {d}", 60)
    # 3000 irrigation + 200 seed + 500 equipment = 3700 total costs
    # Low yield: 50 g/m2 * 10 = 500 kg/ha * 0.22 * 0.8 = 88 credits revenue
    profit = ledger.settle_season(
        grain_g_m2=50.0, crop_key="maize", prices=prices, quarter=3
    )
    assert profit < 0
    assert ledger.balance_credits < 10000


# ---------------------------------------------------------------------------
# AC: seasonal multiplier affects revenue
# ---------------------------------------------------------------------------
def test_seasonal_multiplier_affects_revenue(prices: PriceTable) -> None:
    ledger_q1 = EconomicLedger(balance_credits=0)
    ledger_q1.settle_season(
        grain_g_m2=500.0, crop_key="maize", prices=prices, quarter=1
    )

    ledger_q3 = EconomicLedger(balance_credits=0)
    ledger_q3.settle_season(
        grain_g_m2=500.0, crop_key="maize", prices=prices, quarter=3
    )

    # Q1 multiplier 1.1 > Q3 multiplier 0.8
    assert ledger_q1.season_revenue > ledger_q3.season_revenue


# ---------------------------------------------------------------------------
# AC: credits as integers
# ---------------------------------------------------------------------------
def test_credits_are_integers(prices: PriceTable) -> None:
    ledger = EconomicLedger()
    ledger.settle_season(grain_g_m2=333.3, crop_key="maize", prices=prices, quarter=2)
    assert isinstance(ledger.season_revenue, int)
    assert isinstance(ledger.balance_credits, int)


# ---------------------------------------------------------------------------
# AC: JSON serialization round-trip
# ---------------------------------------------------------------------------
def test_to_dict_from_dict_roundtrip() -> None:
    ledger = EconomicLedger(balance_credits=5000)
    ledger.record_cost(1, "seed", "wheat", 150)
    ledger.record_cost(10, "fertilizer", "urea", 80)
    ledger.season_revenue = 900
    ledger.season_costs = 230
    ledger.season_profit = 670

    d = ledger.to_dict()
    json_str = json.dumps(d)
    restored = EconomicLedger.from_dict(json.loads(json_str))

    # record_cost deducts immediately: 5000 - 150 - 80 = 4770
    assert restored.balance_credits == 4770
    assert len(restored.costs) == 2
    assert restored.costs[0].category == "seed"
    assert restored.season_profit == 670


# ---------------------------------------------------------------------------
# AC: reset_season clears tracking
# ---------------------------------------------------------------------------
def test_reset_season() -> None:
    ledger = EconomicLedger()
    ledger.record_cost(1, "seed", "maize", 200)
    ledger.season_revenue = 500
    ledger.season_costs = 200
    ledger.season_profit = 300
    ledger.reset_season()
    assert ledger.costs == []
    assert ledger.season_revenue == 0
    assert ledger.season_costs == 0
    assert ledger.season_profit == 0
    # Balance reflects costs already deducted (10000 - 200 = 9800), not reset
    assert ledger.balance_credits == 9800


# ---------------------------------------------------------------------------
# AC: area_ha parameter
# ---------------------------------------------------------------------------
def test_area_ha_scales_revenue(prices: PriceTable) -> None:
    ledger_1ha = EconomicLedger(balance_credits=0)
    ledger_1ha.settle_season(
        grain_g_m2=500.0, crop_key="maize", prices=prices, quarter=3, area_ha=1.0
    )
    ledger_5ha = EconomicLedger(balance_credits=0)
    ledger_5ha.settle_season(
        grain_g_m2=500.0, crop_key="maize", prices=prices, quarter=3, area_ha=5.0
    )
    assert ledger_5ha.season_revenue == pytest.approx(
        ledger_1ha.season_revenue * 5, abs=5
    )


# ---------------------------------------------------------------------------
# AC (#371): per-patch revenue accrual — staggered harvests accumulate
# ---------------------------------------------------------------------------
def test_settle_season_accrues_across_patches(prices: PriceTable) -> None:
    """Staggered per-patch settlements add up rather than overwrite (#371).

    Full-field revenue == the sum of area-scaled per-patch settlements because
    ``settle_season`` is area-weighted: Σ(grain_i * area_i) == grain * 1.0 ha.
    """
    staggered = EconomicLedger(balance_credits=0)
    staggered.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.333)
    rev_after_first = staggered.season_revenue
    assert rev_after_first > 0
    staggered.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.334)
    staggered.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.333)

    # Cumulative, not overwritten: later patches added to the running total.
    assert staggered.season_revenue > rev_after_first

    full_field = EconomicLedger(balance_credits=0)
    full_field.settle_season(300.0, "maize", prices, quarter=3, area_ha=1.0)

    # Sum-of-patches == full-field within integer rounding across three patches.
    assert staggered.season_revenue == pytest.approx(full_field.season_revenue, abs=3)
    # Balance rose by exactly the accrued revenue (costs are 0 here).
    assert staggered.balance_credits == staggered.season_revenue


def test_settle_season_profit_tracks_cumulative_revenue(prices: PriceTable) -> None:
    """season_profit stays consistent with cumulative revenue minus costs (#371)."""
    ledger = EconomicLedger(balance_credits=10000)
    ledger.record_cost(0, "seed", "maize", 200)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.5)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.5)
    assert ledger.season_profit == ledger.season_revenue - ledger.season_costs
    assert ledger.season_costs == 200


def test_accrual_resets_between_seasons(prices: PriceTable) -> None:
    """reset_season() clears accrued revenue so seasons stay independent (#371)."""
    ledger = EconomicLedger(balance_credits=0)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.5)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.5)
    season_1 = ledger.season_revenue
    assert season_1 > 0

    ledger.reset_season()
    assert ledger.season_revenue == 0
    assert ledger.season_profit == 0

    # A fresh season accrues from zero, independent of season 1.
    ledger.settle_season(200.0, "maize", prices, quarter=3, area_ha=1.0)
    assert ledger.season_revenue > 0
    assert ledger.season_revenue != season_1


def test_accrual_survives_to_dict_from_dict(prices: PriceTable) -> None:
    """Mid-stagger accrued revenue round-trips through save/load (#371)."""
    ledger = EconomicLedger(balance_credits=0)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.333)
    ledger.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.334)
    mid_revenue = ledger.season_revenue

    restored = EconomicLedger.from_dict(json.loads(json.dumps(ledger.to_dict())))
    assert restored.season_revenue == mid_revenue
    assert restored.balance_credits == ledger.balance_credits

    # Harvesting the remaining patch after reload keeps accruing on top.
    restored.settle_season(300.0, "maize", prices, quarter=3, area_ha=0.333)
    assert restored.season_revenue > mid_revenue
