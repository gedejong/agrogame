"""Tests for player irrigation and fertilizer actions (AGRO-24)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _make_orch(
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
) -> tuple[FullSimulationOrchestrator, str]:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    climate = climates.climates[climate_name]
    orch = FullSimulationOrchestrator(
        profile, crop=crops.crops[crop_name], latitude_deg=climate.latitude_deg
    )
    return orch, climate_name


def _run_season(
    orch: FullSimulationOrchestrator,
    climate_name: str,
    days: int = 150,
    irrigate_mm_per_day: float = 0.0,
    fertilize_n_kg_ha: float = 0.0,
    seed: int = 42,
) -> float:
    """Run a season, optionally applying irrigation and/or fertilizer."""
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates[climate_name]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, date(2024, 4, 1))

    for i, rec in enumerate(series.records):
        if irrigate_mm_per_day > 0:
            orch.apply_irrigation(irrigate_mm_per_day)
        if fertilize_n_kg_ha > 0 and i == 0:
            orch.apply_fertilizer("urea", fertilize_n_kg_ha)
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
    return orch.canopy.state.biomass_g_m2


# ---------------------------------------------------------------------------
# AC3: irrigated maize > rainfed maize in Sahel
# ---------------------------------------------------------------------------
def test_irrigated_maize_outperforms_rainfed_in_sahel() -> None:
    """Irrigated Sahel maize should produce more biomass than rainfed.

    Source: FAO-56 — irrigation increases yield in water-limited environments.
    """
    orch_dry, clim = _make_orch("maize", "sahel_arid")
    biomass_dry = _run_season(orch_dry, clim, irrigate_mm_per_day=0.0)

    orch_wet, clim = _make_orch("maize", "sahel_arid")
    biomass_wet = _run_season(orch_wet, clim, irrigate_mm_per_day=5.0)

    assert biomass_wet > biomass_dry


# ---------------------------------------------------------------------------
# AC4: fertilized maize > unfertilized maize in NL
# ---------------------------------------------------------------------------
def test_fertilized_maize_outperforms_unfertilized_in_nl() -> None:
    """N fertilization should increase biomass when soil N is depleted.

    Source: DSSAT CERES-Maize — N response curves.
    We deplete initial N pools to create N-limited conditions, then
    compare fertilized vs unfertilized.
    """
    # Deplete all N pools (mineral + SOM) to simulate exhausted soil
    orch_unfert, clim = _make_orch("maize", "netherlands_temperate")
    for i in range(len(orch_unfert.n_state.nh4)):
        orch_unfert.n_state.nh4[i] = 0.0
        orch_unfert.n_state.no3[i] = 0.0
        orch_unfert.n_state.organic_n[i] = 0.0
    som = orch_unfert._som_runtime.som
    if som is not None:
        for ly in som.state.layers:
            ly.labile.n_kg_ha = 0.0
            ly.intermediate.n_kg_ha = 0.0
            ly.stable.n_kg_ha = 0.0
    biomass_unfert = _run_season(orch_unfert, clim, fertilize_n_kg_ha=0.0)

    orch_fert, clim = _make_orch("maize", "netherlands_temperate")
    for i in range(len(orch_fert.n_state.nh4)):
        orch_fert.n_state.nh4[i] = 0.0
        orch_fert.n_state.no3[i] = 0.0
        orch_fert.n_state.organic_n[i] = 0.0
    som2 = orch_fert._som_runtime.som
    if som2 is not None:
        for ly in som2.state.layers:
            ly.labile.n_kg_ha = 0.0
            ly.intermediate.n_kg_ha = 0.0
            ly.stable.n_kg_ha = 0.0
    biomass_fert = _run_season(orch_fert, clim, fertilize_n_kg_ha=150.0)

    assert biomass_fert > biomass_unfert


# ---------------------------------------------------------------------------
# AC5: over-irrigation raises theta above field capacity
# ---------------------------------------------------------------------------
def test_over_irrigation_raises_theta_above_fc() -> None:
    """100 mm/day irrigation should push top layer theta above FC.

    Irrigation infiltrates without immediate drainage, so heavy
    application temporarily raises theta above field capacity.
    Drainage occurs during the next step_day() call.
    """
    orch, _ = _make_orch("maize", "sahel_arid")
    fc_top = orch.profile.layers[0].field_capacity
    orch.apply_irrigation(100.0)
    assert orch.water_state.theta[0] > fc_top


# ---------------------------------------------------------------------------
# AC6: urea increases NH4 in top layer
# ---------------------------------------------------------------------------
def test_urea_increases_nh4_top_layer() -> None:
    """Urea application should increase NH4 in the top soil layer."""
    orch, _ = _make_orch()
    nh4_before = orch.n_state.nh4[0]
    orch.apply_fertilizer("urea", 50.0)
    assert orch.n_state.nh4[0] == nh4_before + 50.0


# ---------------------------------------------------------------------------
# Additional: fertilizer type validation
# ---------------------------------------------------------------------------
def test_unknown_fertilizer_raises() -> None:
    orch, _ = _make_orch()
    with pytest.raises(ValueError, match="Unknown fertilizer type"):
        orch.apply_fertilizer("magic_beans", 50.0)


def test_ammonium_nitrate_splits_nh4_no3() -> None:
    """Ammonium nitrate should split 50/50 between NH4 and NO3."""
    orch, _ = _make_orch()
    nh4_before = orch.n_state.nh4[0]
    no3_before = orch.n_state.no3[0]
    orch.apply_fertilizer("ammonium_nitrate", 100.0)
    assert orch.n_state.nh4[0] == pytest.approx(nh4_before + 50.0)
    assert orch.n_state.no3[0] == pytest.approx(no3_before + 50.0)


def test_tsp_increases_available_p() -> None:
    """TSP should increase available P in top layer."""
    orch, _ = _make_orch()
    p_before = orch.p_state.available_p[0]
    orch.apply_fertilizer("tsp", 30.0)
    assert orch.p_state.available_p[0] == p_before + 30.0


def test_invalid_layer_raises() -> None:
    orch, _ = _make_orch()
    with pytest.raises(ValueError, match="Layer .* out of range"):
        orch.apply_fertilizer("urea", 50.0, layer=99)


def test_zero_amount_is_noop() -> None:
    """Zero or negative amounts should be no-ops."""
    orch, _ = _make_orch()
    theta_before = list(orch.water_state.theta)
    nh4_before = orch.n_state.nh4[0]
    orch.apply_irrigation(0.0)
    orch.apply_irrigation(-5.0)
    orch.apply_fertilizer("urea", 0.0)
    orch.apply_fertilizer("urea", -10.0)
    assert orch.water_state.theta == theta_before
    assert orch.n_state.nh4[0] == nh4_before
