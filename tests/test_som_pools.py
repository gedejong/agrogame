"""Tests for three-pool SOM decomposition module (AGRO-103)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.soil.som.pools import (
    SOMLayerPool,
    SOMPoolParams,
    ThreePoolSOM,
    steady_state_fractions,
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
        # Stable > intermediate > labile (kinetic steady state)
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


# ---------------------------------------------------------------------------
# Initial pool sizing at the kinetic steady state
# ---------------------------------------------------------------------------
class TestSteadyStateInitialisation:
    def test_fallow_conditioning_preserves_stock_and_starts_flux_counters_at_zero(
        self,
    ) -> None:
        profile = load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]
        prior = ThreePoolSOM(SOMPoolParams(initial_fallow_days=0), len(profile.layers))
        settled = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        prior.initialize_from_profile(profile)
        settled.initialize_from_profile(profile)
        for before, after in zip(
            prior.state.layers, settled.state.layers, strict=False
        ):
            assert after.total_c == pytest.approx(before.total_c)
            assert after.labile.c_kg_ha < before.labile.c_kg_ha
            assert after.cumulative_co2_c_kg_ha == 0.0

    def test_negative_fallow_interval_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="initial_fallow_days"):
            ThreePoolSOM(SOMPoolParams(initial_fallow_days=-1), 1)

    def test_loam_shares_lie_in_the_equilibrium_bands(self) -> None:
        """~2 % labile, ~30 % intermediate, remainder stable on a loam.

        RothC equilibrium pools for arable topsoil hold a few per cent of C in
        the fast pools (DPM + BIO) and the bulk in HUM (Coleman & Jenkinson
        1996); the analytical steady state of this module's kinetics lands in
        the same bands.
        """
        lab, inter, stb = steady_state_fractions(SOMPoolParams(), clay_pct=22.0)
        assert lab + inter + stb == pytest.approx(1.0)
        assert 0.01 <= lab <= 0.03
        assert 0.25 <= inter <= 0.40
        assert stb > inter > lab

    def test_clay_protection_shifts_carbon_towards_the_stable_pool(self) -> None:
        """Protection slows the slow pools most, so clays hold less labile C."""
        params = SOMPoolParams()
        lab_sand, _, stb_sand = steady_state_fractions(params, clay_pct=5.0)
        lab_clay, _, stb_clay = steady_state_fractions(params, clay_pct=50.0)
        assert lab_clay < lab_sand
        assert stb_clay > stb_sand

    def test_steady_state_pools_hold_under_a_matching_input(self) -> None:
        """Pools sized by the formula stay put when fed the input it assumes.

        With env_f = 1 (25 °C, 60 % WFPS), no priming and no aggregation the
        labile pool loses C_lab * k_lab * pf per day, so an equal daily input
        must leave every pool where it started. The labile pool settles one
        day's input (k * dt = 5 %) below the continuous-time value because
        ``daily_step`` adds the input before decomposing; the slow pools move
        by far less than 1 %.
        """
        params = SOMPoolParams()
        clay = 22.0
        som = ThreePoolSOM(params, n_layers=1)
        lab, inter, stb = steady_state_fractions(params, clay)
        total_c = 40_000.0
        layer = som.state.layers[0]
        layer.labile = SOMLayerPool(c_kg_ha=total_c * lab, n_kg_ha=total_c * lab / 12)
        layer.intermediate = SOMLayerPool(
            c_kg_ha=total_c * inter, n_kg_ha=total_c * inter / 15
        )
        layer.stable = SOMLayerPool(c_kg_ha=total_c * stb, n_kg_ha=total_c * stb / 20)
        pf_lab = som._protection_factor(params.protection_frac_labile, clay, 0)
        daily_input = layer.labile.c_kg_ha * params.k_labile * pf_lab
        start = (layer.labile.c_kg_ha, layer.intermediate.c_kg_ha, layer.stable.c_kg_ha)

        for _ in range(60):
            som.daily_step(
                0,
                temp_c=25.0,
                wfps=0.6,
                fresh_c_input=daily_input,
                fresh_n_input=daily_input / 12.0,
                clay_pct=clay,
            )

        assert layer.labile.c_kg_ha == pytest.approx(start[0], rel=0.06)
        assert layer.intermediate.c_kg_ha == pytest.approx(start[1], rel=0.01)
        assert layer.stable.c_kg_ha == pytest.approx(start[2], rel=0.01)

    def test_depth_attenuation_moves_deep_carbon_into_the_stable_pool(self) -> None:
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)

        labile = [ly.labile.c_kg_ha / ly.total_c for ly in som.state.layers]
        stable = [ly.stable.c_kg_ha / ly.total_c for ly in som.state.layers]
        assert labile == sorted(labile, reverse=True)
        assert labile[0] > 2 * labile[-1]
        assert stable == sorted(stable)
        # Fallow conditioning reduces the fast pool below the input-fed prior.
        lab_top, _, _ = steady_state_fractions(
            som.params, profile.layers[0].clay_pct or 22.0
        )
        assert 0.0 < labile[0] < lab_top

    def test_disabled_attenuation_gives_depth_uniform_shares(self) -> None:
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        params = SOMPoolParams(fresh_input_efolding_depth_cm=0.0)
        som = ThreePoolSOM(params, len(profile.layers))
        som.initialize_from_profile(profile)

        labile = [ly.labile.c_kg_ha / ly.total_c for ly in som.state.layers]
        assert max(labile) == pytest.approx(min(labile))

    def test_total_carbon_follows_organic_matter_not_the_split(self) -> None:
        """Total C per layer = OM% x bulk density x depth x 0.58 (van Bemmelen)."""
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)

        for soil_layer, layer in zip(profile.layers, som.state.layers, strict=True):
            expected_c = (
                soil_layer.organic_matter_pct
                / 100.0
                * soil_layer.bulk_density_g_cm3
                * 1000.0
                * soil_layer.depth_cm
                / 100.0
                * 10_000.0
                * 0.58
            )
            assert layer.total_c == pytest.approx(expected_c)


class TestFirstSeasonMineralisation:
    """Season-scale net N mineralisation from the initial pools (standalone).

    Loam profile, 150-day season at 17 °C and 60 % WFPS, no fresh input.
    """

    @staticmethod
    def _season_net_n(
        som: ThreePoolSOM, profile: object, days: int = 150, temp_c: float = 17.0
    ) -> list[float]:
        layers = profile.layers  # type: ignore[attr-defined]
        totals = [0.0] * len(layers)
        for _ in range(days):
            for i, soil_layer in enumerate(layers):
                fluxes = som.daily_step(
                    i, temp_c=temp_c, wfps=0.6, clay_pct=soil_layer.clay_pct or 22.0
                )
                totals[i] += fluxes.mineralized_n_kg_ha
        return totals

    def test_first_season_topsoil_net_mineralisation_is_a_few_percent_of_organic_n(
        self,
    ) -> None:
        """Net mineralisation over one warm season stays <= 5 % of topsoil organic N.

        Field soils mineralise roughly 1-3 % of their organic N per year
        (Stanford & Smith 1972), so a single 150-day season at 17 °C should
        release a few per cent of the topsoil organic N at most. Measured
        ~4.3 % with the steady-state split (the fixed 5/20/75 split gave ~6.8 %).
        The floor guards against a silently broken source.
        """
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)
        organic_n_topsoil = som.state.layers[0].total_n

        season = self._season_net_n(som, profile)
        fraction = season[0] / organic_n_topsoil
        assert 0.02 <= fraction <= 0.05, (
            f"season-1 topsoil net mineralisation {season[0]:.0f} kg N/ha is "
            f"{100 * fraction:.1f} % of {organic_n_topsoil:.0f} kg organic N/ha"
        )

    def test_three_seasons_supply_stays_within_factor_one_point_five(self) -> None:
        """Issue #435: no first-season spike under the actual no-input forcing."""
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        som = ThreePoolSOM(SOMPoolParams(), len(profile.layers))
        som.initialize_from_profile(profile)

        season_1 = sum(self._season_net_n(som, profile))
        season_2 = sum(self._season_net_n(som, profile))
        season_3 = sum(self._season_net_n(som, profile))
        assert min(season_1, season_2, season_3) > 0.0
        assert (
            max(season_1, season_2, season_3) / min(season_1, season_2, season_3) < 1.5
        )
