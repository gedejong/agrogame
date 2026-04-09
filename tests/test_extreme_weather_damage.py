"""Tests for extreme weather damage: frost, heat, waterlogging (#34).

Verifies that frost, heat waves, and waterlogging cause appropriate
crop damage, and that recovery resets counters when conditions normalize.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers


def _make_orch(
    crop_key: str = "maize",
    soil_key: str = "loam_temperate",
) -> FullSimulationOrchestrator:
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    return FullSimulationOrchestrator(
        soils.soils[soil_key],
        event_bus=EventBus(),
        crop=crops.crops[crop_key],
    )


def _step(
    orch: FullSimulationOrchestrator,
    n: int,
    *,
    tmin: float = 15.0,
    tmax: float = 28.0,
    rain: float = 3.0,
    start_day: int = 0,
) -> None:
    start = date(2024, 5, 1) + timedelta(days=start_day)
    for d in range(n):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rain),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=18.0,
            sim_date=start + timedelta(days=d),
        )


def test_frost_during_flowering_reduces_lai() -> None:
    """Frost (tmin < 0C) during early growth should reduce LAI."""
    control = _make_orch()
    frost = _make_orch()
    # Grow both to emergence + early growth (15 days)
    _step(control, 15)
    _step(frost, 15)
    lai_before = frost.canopy.state.lai
    assert lai_before > 0.1, "Should have some LAI before frost"
    # Apply frost: 3 days of tmin=-5C
    _step(frost, 3, tmin=-5.0, tmax=5.0, start_day=15)
    _step(control, 3, start_day=15)
    assert frost.canopy.state.lai < control.canopy.state.lai, (
        f"Frost LAI ({frost.canopy.state.lai:.2f}) should be less than "
        f"control ({control.canopy.state.lai:.2f})"
    )


def test_frost_severity_proportional() -> None:
    """Colder frost should cause more damage than mild frost."""
    mild = _make_orch()
    severe = _make_orch()
    _step(mild, 15)
    _step(severe, 15)
    # Mild frost: tmin = -1C (just below 0C threshold)
    _step(mild, 1, tmin=-1.0, tmax=5.0, start_day=15)
    # Severe frost: tmin = -10C
    _step(severe, 1, tmin=-10.0, tmax=0.0, start_day=15)
    assert (
        severe.canopy.state.lai < mild.canopy.state.lai
    ), "Severe frost should cause more LAI loss than mild frost"


def test_heat_during_flowering_reduces_grain() -> None:
    """Heat wave (tmax > 35C) during flowering should reduce grain yield."""
    # Use spring wheat with lower heat threshold (32C) and shorter cycle
    control = _make_orch("spring_wheat")
    heat = _make_orch("spring_wheat")
    # Grow to flowering: spring wheat flowers at ~600 GDD.
    # With tmin=5, tmax=20 (Tbase=0): GDD/day = 12.5, so ~48 days to flower.
    _step(control, 55, tmin=5.0, tmax=20.0)
    _step(heat, 55, tmin=5.0, tmax=20.0)
    # Both should be in FLOWERING or GRAIN_FILL by now
    # Apply 5 days of heat during grain fill
    _step(heat, 5, tmin=25.0, tmax=40.0, start_day=55)
    _step(control, 5, tmin=15.0, tmax=28.0, start_day=55)
    # Continue to maturity
    _step(heat, 40, tmin=15.0, tmax=28.0, start_day=60)
    _step(control, 40, tmin=15.0, tmax=28.0, start_day=60)
    # Heat should have reduced grain vs control
    assert heat.canopy.state.grain_biomass_g_m2 < (
        control.canopy.state.grain_biomass_g_m2
    ), (
        f"Heat grain ({heat.canopy.state.grain_biomass_g_m2:.1f}) should be "
        f"less than control ({control.canopy.state.grain_biomass_g_m2:.1f})"
    )


def test_heat_grain_reduction_isolated() -> None:
    """Heat just above threshold reduces grain without killing growth.

    Uses tmax=36C (just above maize 35C threshold) so cardinal_temp_factor
    is still positive (tmean=25.5, well below temp_max_c=42). This isolates
    the heat_grain_reduction mechanism from temperature-growth suppression.
    """
    control = _make_orch("maize")
    heat = _make_orch("maize")
    # Grow to grain fill: maize flowers ~759 GDD, grain fill starts after.
    # With tmin=15, tmax=28 (Tbase=8): GDD/day=13.5, flower ~day 56.
    _step(control, 65, tmin=15.0, tmax=28.0)
    _step(heat, 65, tmin=15.0, tmax=28.0)
    # Both in GRAIN_FILL now. Apply heat: tmax=36C (just above 35C threshold)
    _step(heat, 10, tmin=15.0, tmax=36.0, start_day=65)
    _step(control, 10, tmin=15.0, tmax=28.0, start_day=65)
    # Continue
    _step(heat, 30, tmin=15.0, tmax=28.0, start_day=75)
    _step(control, 30, tmin=15.0, tmax=28.0, start_day=75)
    assert heat.canopy.state.grain_biomass_g_m2 < (
        control.canopy.state.grain_biomass_g_m2
    ), (
        f"Heat grain ({heat.canopy.state.grain_biomass_g_m2:.1f}) should be "
        f"less than control ({control.canopy.state.grain_biomass_g_m2:.1f}) "
        f"with targeted heat just above threshold"
    )


def test_waterlogging_reduces_lai() -> None:
    """Waterlogging (saturated soil) should reduce LAI after threshold days."""
    control = _make_orch("soybean")  # Soybean: 2-day waterlog threshold
    waterlogged = _make_orch("soybean")
    _step(control, 20)
    _step(waterlogged, 20)
    # Force saturation via irrigation (bypasses SCS runoff)
    for _ in range(5):
        waterlogged.apply_irrigation(200.0)  # saturate top layer
        _step(waterlogged, 1, start_day=20)
    _step(control, 5, rain=3.0, start_day=20)
    assert waterlogged.canopy.state.lai < control.canopy.state.lai, (
        f"Waterlogged LAI ({waterlogged.canopy.state.lai:.2f}) should be "
        f"less than control ({control.canopy.state.lai:.2f})"
    )


def test_recovery_after_frost() -> None:
    """After frost ends, growth should resume (no permanent counter block)."""
    orch = _make_orch()
    _step(orch, 15)
    lai_after_frost_start = orch.canopy.state.lai
    # 1 day frost
    _step(orch, 1, tmin=-3.0, tmax=5.0, start_day=15)
    lai_after_frost = orch.canopy.state.lai
    assert lai_after_frost < lai_after_frost_start
    # 10 more warm days — growth should resume
    _step(orch, 10, start_day=16)
    assert (
        orch.canopy.state.lai > lai_after_frost
    ), "Growth should resume after frost ends"


def test_no_frost_damage_before_emergence() -> None:
    """Frost before emergence (planted/pre-emerged) should not damage LAI."""
    orch = _make_orch()
    # Day 1 only — maize not yet emerged (needs ~100 GDD)
    _step(orch, 1, tmin=-5.0, tmax=2.0)
    # LAI should still be 0 (not emerged yet)
    assert orch.canopy.state.lai == 0.0


def test_params_loaded_from_yaml() -> None:
    """Per-crop extreme weather params should load correctly."""
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    maize = crops.crops["maize"]
    assert maize.canopy.frost_threshold_c == 0.0
    assert maize.canopy.heat_damage_threshold_c == 35.0
    wheat = crops.crops["winter_wheat"]
    assert wheat.canopy.frost_threshold_c == -2.0
    assert wheat.canopy.heat_damage_threshold_c == 32.0
    rice = crops.crops["rice"]
    assert rice.canopy.frost_threshold_c == 10.0
    assert rice.canopy.waterlog_days_for_damage == 7  # paddy rice tolerant
