"""Tests for three-pool SOM decomposition module (AGRO-103)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.soil.som.pools import (
    SOMLayerPool,
    SOMPoolParams,
    ThreePoolSOM,
)
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import TEXTURE_TO_CLAY


# ---------------------------------------------------------------------------
# AC: Three pools per layer with C and N
# ---------------------------------------------------------------------------
class TestThreePoolStructure:
    def test_three_pools_exist(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), n_layers=3)
        layer = som.state.layers[0]
        assert hasattr(layer, "labile")
        assert hasattr(layer, "intermediate")
        assert hasattr(layer, "stable")

    def test_cn_tracking(self) -> None:
        pool = SOMLayerPool(c_kg_ha=1200.0, n_kg_ha=100.0)
        assert pool.cn_ratio == pytest.approx(12.0)


# ---------------------------------------------------------------------------
# AC: Initialize from profile
# ---------------------------------------------------------------------------
class TestInitFromProfile:
    def test_initialization_distributes_om(self) -> None:
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)

        layer = som.state.layers[0]
        assert layer.labile.c_kg_ha > 0
        assert layer.intermediate.c_kg_ha > 0
        assert layer.stable.c_kg_ha > 0
        # Stable > intermediate > labile (75/20/5 split)
        assert layer.stable.c_kg_ha > layer.intermediate.c_kg_ha
        assert layer.intermediate.c_kg_ha > layer.labile.c_kg_ha

    def test_n_initialized_from_cn_ratios(self) -> None:
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)

        layer = som.state.layers[0]
        assert layer.labile.cn_ratio == pytest.approx(12.0, abs=0.1)
        assert layer.intermediate.cn_ratio == pytest.approx(15.0, abs=0.1)
        assert layer.stable.cn_ratio == pytest.approx(20.0, abs=0.1)


# ---------------------------------------------------------------------------
# AC: First-order decomposition with Q10 and moisture
# ---------------------------------------------------------------------------
class TestDecompositionKinetics:
    def test_decomposition_reduces_pool(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), n_layers=1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        c_before = som.state.layers[0].labile.c_kg_ha
        som.daily_step(0, temp_c=25.0, wfps=0.6)
        assert som.state.layers[0].labile.c_kg_ha < c_before

    def test_q10_temperature_sensitivity(self) -> None:
        """Warmer → faster decomposition (Q10 ≈ 2)."""
        params = SOMPoolParams()
        som_cold = ThreePoolSOM(params, 1)
        som_cold.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        fluxes_cold = som_cold.daily_step(0, temp_c=15.0, wfps=0.6)

        som_warm = ThreePoolSOM(params, 1)
        som_warm.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        fluxes_warm = som_warm.daily_step(0, temp_c=25.0, wfps=0.6)

        assert fluxes_warm.decomposed_c_kg_ha > fluxes_cold.decomposed_c_kg_ha

    def test_moisture_optimum_at_60_wfps(self) -> None:
        """Decomposition peaks at 60% WFPS (Linn & Doran 1984)."""
        assert ThreePoolSOM._moisture_factor(0.6) == pytest.approx(1.0)
        assert ThreePoolSOM._moisture_factor(0.3) < 1.0
        assert ThreePoolSOM._moisture_factor(0.9) < 1.0
        assert ThreePoolSOM._moisture_factor(0.0) == 0.0


# ---------------------------------------------------------------------------
# AC: Pool transfers (humification)
# ---------------------------------------------------------------------------
class TestHumification:
    def test_labile_transfers_to_intermediate(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        inter_before = som.state.layers[0].intermediate.c_kg_ha
        som.daily_step(0, temp_c=25.0, wfps=0.6)
        assert som.state.layers[0].intermediate.c_kg_ha > inter_before


# ---------------------------------------------------------------------------
# AC: Priming from fresh organic inputs
# ---------------------------------------------------------------------------
class TestPriming:
    def test_priming_increases_decomposition(self) -> None:
        """Priming multiplier > 1 should increase labile decomposition."""
        params = SOMPoolParams()
        som_no_prime = ThreePoolSOM(params, 1)
        som_no_prime.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        flux_no = som_no_prime.daily_step(
            0, temp_c=25.0, wfps=0.6, priming_multiplier=1.0
        )

        som_primed = ThreePoolSOM(params, 1)
        som_primed.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        flux_pr = som_primed.daily_step(
            0, temp_c=25.0, wfps=0.6, priming_multiplier=1.5
        )

        assert flux_pr.decomposed_c_kg_ha > flux_no.decomposed_c_kg_ha


# ---------------------------------------------------------------------------
# AC: N mining under high C:N inputs
# ---------------------------------------------------------------------------
class TestNMining:
    def test_high_cn_residue_causes_immobilization(self) -> None:
        """Adding high-C residue (C:N > 25) should immobilize mineral N."""
        som = ThreePoolSOM(SOMPoolParams(), 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=100.0, n_kg_ha=8.3)
        # Add high-C:N fresh input (C:N = 80)
        fluxes = som.daily_step(
            0, temp_c=25.0, wfps=0.6, fresh_c_input=400.0, fresh_n_input=5.0
        )
        assert fluxes.immobilized_n_kg_ha > 0


# ---------------------------------------------------------------------------
# AC: CO2 emissions tracked
# ---------------------------------------------------------------------------
class TestCO2Tracking:
    def test_co2_emitted_on_decomposition(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        fluxes = som.daily_step(0, temp_c=25.0, wfps=0.6)
        assert fluxes.co2_c_kg_ha > 0

    def test_cumulative_co2_tracked(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=1000.0, n_kg_ha=83.3)
        som.daily_step(0, temp_c=25.0, wfps=0.6)
        assert som.state.layers[0].cumulative_co2_c_kg_ha > 0


# ---------------------------------------------------------------------------
# AC: MGE 15-60% depending on substrate quality
# ---------------------------------------------------------------------------
class TestMGE:
    def test_mge_range(self) -> None:
        params = SOMPoolParams()
        assert 0.15 <= params.mge_stable <= 0.60
        assert 0.15 <= params.mge_intermediate <= 0.60
        assert 0.15 <= params.mge_labile <= 0.60


# ---------------------------------------------------------------------------
# AC: Mass balance closure within 0.1% daily
# ---------------------------------------------------------------------------
class TestMassBalance:
    def test_daily_mass_balance(self) -> None:
        som = ThreePoolSOM(SOMPoolParams(), 1)
        som.state.layers[0].labile = SOMLayerPool(c_kg_ha=500.0, n_kg_ha=41.7)
        som.state.layers[0].intermediate = SOMLayerPool(c_kg_ha=2000.0, n_kg_ha=133.3)
        som.state.layers[0].stable = SOMLayerPool(c_kg_ha=7500.0, n_kg_ha=375.0)
        total_c_before = som.state.layers[0].total_c
        fluxes = som.daily_step(0, temp_c=25.0, wfps=0.6)
        total_c_after = som.state.layers[0].total_c
        # C_before = C_after + CO2 + microbial_C
        c_accounted = total_c_after + fluxes.co2_c_kg_ha + fluxes.microbial_c_kg_ha
        error = abs(c_accounted - total_c_before) / total_c_before
        assert error < 0.001


# ---------------------------------------------------------------------------
# AC: Labile turnover 10-50 days at 25°C
# ---------------------------------------------------------------------------
class TestTurnoverRates:
    def test_labile_turnover(self) -> None:
        """Labile pool turnover ~20 days at 25°C, 60% WFPS."""
        params = SOMPoolParams()
        # turnover = 1/k = 1/0.05 = 20 days
        assert 10 <= 1.0 / params.k_labile <= 50

    def test_intermediate_turnover(self) -> None:
        """Intermediate ~3 years."""
        params = SOMPoolParams()
        turnover_years = 1.0 / (params.k_intermediate * 365)
        assert 0.5 <= turnover_years <= 5.0

    def test_stable_turnover(self) -> None:
        """Stable ~55 years."""
        params = SOMPoolParams()
        turnover_years = 1.0 / (params.k_stable * 365)
        assert 20 <= turnover_years <= 1000


# ---------------------------------------------------------------------------
# AC: clay_pct field on SoilLayer
# ---------------------------------------------------------------------------
class TestClayPct:
    def test_texture_to_clay_lookup(self) -> None:
        assert TEXTURE_TO_CLAY["clay"] == 50.0
        assert TEXTURE_TO_CLAY["loam"] == 22.0

    def test_clay_pct_derived_from_texture(self) -> None:
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        for layer in profile.layers:
            assert layer.clay_pct is not None
            assert layer.clay_pct > 0


# ---------------------------------------------------------------------------
# AC: SoilSnapshot includes SOM state
# ---------------------------------------------------------------------------
class TestSnapshotSOM:
    def test_snapshot_has_som_fields(self) -> None:
        from agrogame.sim.orchestrator import SoilSnapshot

        snap = SoilSnapshot(
            som_labile_c=[100.0],
            som_labile_n=[8.3],
            som_intermediate_c=[400.0],
            som_intermediate_n=[26.7],
            som_stable_c=[1500.0],
            som_stable_n=[75.0],
        )
        d = snap.to_dict()
        assert "som_labile_c" in d
        restored = SoilSnapshot.from_dict(d)
        assert restored.som_labile_c == [100.0]
