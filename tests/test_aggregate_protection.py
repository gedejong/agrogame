"""Tests for SOM aggregate protection (AGRO-104)."""

from __future__ import annotations

import pytest

from agrogame.soil.som.pools import (
    SOMLayerPool,
    SOMPoolParams,
    ThreePoolSOM,
)


# ---------------------------------------------------------------------------
# AC: Protection fraction reduces decomposition 50-80%
# ---------------------------------------------------------------------------
class TestProtectionReduction:
    def test_protection_reduces_decomposition(self) -> None:
        """Protected fraction decomposes slower than unprotected."""
        params = SOMPoolParams()
        # High clay = more protection
        som_clay = ThreePoolSOM(params, 1)
        som_clay.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000, n_kg_ha=83)
        flux_clay = som_clay.daily_step(0, temp_c=25.0, wfps=0.6, clay_pct=50.0)

        # No clay = no protection
        som_sand = ThreePoolSOM(params, 1)
        som_sand.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000, n_kg_ha=83)
        flux_sand = som_sand.daily_step(0, temp_c=25.0, wfps=0.6, clay_pct=0.0)

        assert flux_clay.decomposed_c_kg_ha < flux_sand.decomposed_c_kg_ha

    def test_protection_reduction_in_range(self) -> None:
        """Protection should reduce decomposition by 50-80%."""
        params = SOMPoolParams()
        assert 0.50 <= params.protection_reduction <= 0.80


# ---------------------------------------------------------------------------
# AC: Clay scaling
# ---------------------------------------------------------------------------
class TestClayScaling:
    def test_higher_clay_more_protection(self) -> None:
        """Higher clay% → more protection → less decomposition."""
        params = SOMPoolParams()
        results = []
        for clay in [5.0, 22.0, 50.0]:
            som = ThreePoolSOM(params, 1)
            som.state.layers[0].intermediate = SOMLayerPool(c_kg_ha=2000, n_kg_ha=133)
            flux = som.daily_step(0, temp_c=25.0, wfps=0.6, clay_pct=clay)
            results.append(flux.decomposed_c_kg_ha)
        # Sand (5%) > loam (22%) > clay (50%)
        assert results[0] > results[1] > results[2]

    def test_protection_factor_at_zero_clay(self) -> None:
        """At 0% clay, protection factor should be 1.0 (no protection)."""
        som = ThreePoolSOM(SOMPoolParams(), 1)
        pf = som._protection_factor(0.4, clay_pct=0.0)
        assert pf == pytest.approx(1.0)

    def test_protection_factor_at_full_clay(self) -> None:
        """At 40% clay (scale point), protection is at full base fraction."""
        som = ThreePoolSOM(SOMPoolParams(), 1)
        pf = som._protection_factor(0.4, clay_pct=40.0)
        # 1.0 - 0.4 * 0.70 = 0.72
        assert pf == pytest.approx(0.72, abs=0.01)


# ---------------------------------------------------------------------------
# AC: Clay soil retains more SOM over 365 days
# ---------------------------------------------------------------------------
def test_clay_retains_more_som_365d() -> None:
    """Clay soil should retain more SOM than sandy soil over 1 year.

    Ref: Six et al. (2002) — clay minerals stabilize SOM in aggregates.
    """
    params = SOMPoolParams()

    def run_365(clay_pct: float) -> float:
        som = ThreePoolSOM(params, 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=500, n_kg_ha=42)
        som.state.layers[0].intermediate = SOMLayerPool(c_kg_ha=2000, n_kg_ha=133)
        som.state.layers[0].stable = SOMLayerPool(c_kg_ha=7500, n_kg_ha=375)
        initial_c = som.state.layers[0].total_c
        for _ in range(365):
            som.daily_step(0, temp_c=20.0, wfps=0.5, clay_pct=clay_pct)
        return som.state.layers[0].total_c / initial_c

    retention_sand = run_365(5.0)
    retention_clay = run_365(50.0)
    assert retention_clay > retention_sand


# ---------------------------------------------------------------------------
# AC: Wet-dry cycling increases CO2 (Birch effect)
# ---------------------------------------------------------------------------
def test_birch_effect_co2_pulse() -> None:
    """Wet-dry cycle should produce a CO2 pulse (Birch 1958).

    The disruption releases protected SOM, increasing decomposition.
    """
    params = SOMPoolParams()

    # Baseline: constant moisture
    som_const = ThreePoolSOM(params, 1)
    som_const.state.layers[0].intermediate = SOMLayerPool(c_kg_ha=2000, n_kg_ha=133)
    co2_const = 0.0
    for _ in range(10):
        flux = som_const.daily_step(0, temp_c=25.0, wfps=0.5, clay_pct=30.0)
        co2_const += flux.co2_c_kg_ha

    # With disruption: apply wet-dry event at day 5
    som_wd = ThreePoolSOM(params, 1)
    som_wd.state.layers[0].intermediate = SOMLayerPool(c_kg_ha=2000, n_kg_ha=133)
    co2_wd = 0.0
    for d in range(10):
        if d == 5:
            som_wd.apply_wet_dry_disruption(0)
        flux = som_wd.daily_step(0, temp_c=25.0, wfps=0.5, clay_pct=30.0)
        co2_wd += flux.co2_c_kg_ha

    assert co2_wd > co2_const


# ---------------------------------------------------------------------------
# AC: Configurable per soil type
# ---------------------------------------------------------------------------
class TestConfigurable:
    def test_params_configurable(self) -> None:
        params = SOMPoolParams(
            protection_frac_labile=0.20,
            protection_frac_intermediate=0.50,
            protection_frac_stable=0.70,
            protection_reduction=0.60,
        )
        assert params.protection_frac_labile == 0.20
        assert params.protection_reduction == 0.60
