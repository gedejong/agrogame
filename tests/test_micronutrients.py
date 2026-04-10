"""Tests for micronutrient cycling: Fe, Zn, Mn (#214).

Literature-cited quantitative assertions for scientific accuracy.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.soil.water.types import DailyDrivers
from agrogame.plant.events import NutrientStressComputed
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.micronutrients.cycle import MicronutrientCycle, _interpolate_ph
from agrogame.soil.micronutrients.constants import (
    PH_AVAIL_FE,
    PH_AVAIL_ZN,
    PH_AVAIL_MN,
)
from agrogame.soil.micronutrients.params import MicronutrientParams
from agrogame.soil.micronutrients.state import MicronutrientState


# --- Unit: pH-availability lookup ---


def test_ph_availability_fe_drops_above_7() -> None:
    """Fe availability should drop sharply above pH 7.

    Ref: Lindsay 1979, Chemical Equilibria in Soils.
    """
    mult_65 = _interpolate_ph(6.5, PH_AVAIL_FE)
    mult_80 = _interpolate_ph(8.0, PH_AVAIL_FE)
    assert (
        mult_65 > mult_80 * 3
    ), f"Fe at pH 6.5 ({mult_65:.2f}) should be >3x pH 8.0 ({mult_80:.2f})"


def test_ph_availability_zn_drops_above_7() -> None:
    """Zn availability drops above pH 7.

    Ref: Alloway 2008, Micronutrient Deficiencies.
    """
    mult_65 = _interpolate_ph(6.5, PH_AVAIL_ZN)
    mult_80 = _interpolate_ph(8.0, PH_AVAIL_ZN)
    assert mult_65 > mult_80 * 2


def test_ph_availability_mn_drops_above_7() -> None:
    """Mn availability drops above pH 7.

    Ref: Lindsay 1979.
    """
    mult_55 = _interpolate_ph(5.5, PH_AVAIL_MN)
    mult_80 = _interpolate_ph(8.0, PH_AVAIL_MN)
    assert mult_55 > mult_80 * 3


# --- Unit: default pool ranges ---


def test_default_pools_in_range() -> None:
    """Default DTPA-extractable Fe should be 2-20 ppm.

    Ref: Sims & Johnson 1991, Soil Testing.
    """
    state = MicronutrientState.from_layers(3)
    assert (
        2.0 <= state.fe_available[0] <= 20.0
    ), f"Fe available {state.fe_available[0]:.1f} ppm, expected 2-20"
    assert (
        0.5 <= state.zn_available[0] <= 5.0
    ), f"Zn available {state.zn_available[0]:.1f} ppm, expected 0.5-5"
    assert (
        1.0 <= state.mn_available[0] <= 50.0
    ), f"Mn available {state.mn_available[0]:.1f} ppm, expected 1-50"


# --- Unit: stress computation ---


def test_deficiency_stress_below_critical() -> None:
    """When available Fe < critical, stress should be < 1.0."""
    bus = EventBus()
    state = MicronutrientState.from_layers(1)
    state.fe_available[0] = 2.0  # below CRITICAL_FE_PPM (4.5)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    flux = cycle.daily_step(biomass_inc_g_m2=20.0)
    assert (
        flux.fe_stress < 1.0
    ), f"Fe stress should be < 1.0 when below critical, got {flux.fe_stress:.2f}"


def test_no_stress_above_critical() -> None:
    """When available Fe > critical, stress should be 1.0."""
    bus = EventBus()
    state = MicronutrientState.from_layers(1)
    state.fe_available[0] = 15.0  # well above critical
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    flux = cycle.daily_step(biomass_inc_g_m2=20.0)
    assert (
        flux.fe_stress >= 0.9
    ), f"Fe stress should be ~1.0 when above critical, got {flux.fe_stress:.2f}"


# --- Unit: OM complexation ---


def test_om_complexation_reduces_availability() -> None:
    """High SOM should reduce available micronutrient fraction.

    Ref: Stevenson 1991, Humus Chemistry.
    """
    bus = EventBus()
    state = MicronutrientState.from_layers(1)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    # Low SOM
    cycle.set_som_c([100.0])
    cycle.daily_step(biomass_inc_g_m2=0.0)
    fe_low_som = state.fe_available[0]
    # High SOM — reset state
    state2 = MicronutrientState.from_layers(1)
    cycle2 = MicronutrientCycle(bus, state2, MicronutrientParams(), 1)
    cycle2.set_som_c([2000.0])
    cycle2.daily_step(biomass_inc_g_m2=0.0)
    fe_high_som = state2.fe_available[0]
    assert (
        fe_high_som < fe_low_som
    ), f"High SOM Fe ({fe_high_som:.2f}) should be < low SOM ({fe_low_som:.2f})"


# --- Unit: amendment ---


def test_amendment_increases_availability() -> None:
    """ZnSO4 application should increase available Zn."""
    bus = EventBus()
    state = MicronutrientState.from_layers(1)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    before = state.zn_available[0]
    cycle.apply_amendment("zn", 500.0)  # 500 g/ha ZnSO4
    after = state.zn_available[0]
    assert after > before, "Amendment should increase Zn availability"


# --- Unit: stress events emitted ---


def test_stress_events_emitted() -> None:
    """NutrientStressComputed should be emitted for Fe, Zn, Mn."""
    bus = EventBus()
    events: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, events.append)
    state = MicronutrientState.from_layers(1)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    cycle.daily_step(biomass_inc_g_m2=20.0)
    nutrients = {e.nutrient for e in events}
    assert "Fe" in nutrients
    assert "Zn" in nutrients
    assert "Mn" in nutrients


# --- Integration: orchestrator wiring ---


def test_soil_specific_micronutrient_pools() -> None:
    """Sandy arid soil should have lower Fe/Zn than loam.

    Ref: Sims & Johnson 1991 — sandy soils have lower DTPA-extractable levels.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    sandy = FullSimulationOrchestrator(
        soils.soils["sandy_arid"],
        event_bus=EventBus(),
    )
    loam = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
    )
    assert (
        sandy.micro_state.fe_available[0] < loam.micro_state.fe_available[0]
    ), "Sandy Fe should be < loam Fe"
    assert (
        sandy.micro_state.zn_available[0] < loam.micro_state.zn_available[0]
    ), "Sandy Zn should be < loam Zn"


def _make_orch() -> FullSimulationOrchestrator:
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    return FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )


def test_orchestrator_has_micronutrient_state() -> None:
    orch = _make_orch()
    assert hasattr(orch, "micro_state")
    assert len(orch.micro_state.fe_available) > 0


def test_snapshot_preserves_micronutrients() -> None:
    orch = _make_orch()
    orch.micro_state.fe_available[0] = 5.0
    snap = orch.snapshot_soil()
    assert snap.micro_fe_avail[0] == 5.0
    orch.micro_state.fe_available[0] = 15.0
    orch.restore_soil(snap)
    assert orch.micro_state.fe_available[0] == 5.0


def test_multi_season_pool_continuity() -> None:
    """Micronutrient pools should persist across harvest + reset_crop.

    Amendment in season 1 should still be visible in season 2.
    """

    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )
    # Apply Zn amendment in season 1
    orch.micro_cycle.apply_amendment("zn", 1000.0)
    start = date(2024, 5, 1)
    for d in range(10):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=3.0),
            tmin_c=15.0,
            tmax_c=28.0,
            par_mj_m2=18.0,
            sim_date=start + timedelta(days=d),
        )
    # Harvest and reset
    _ = orch.harvest()
    orch.reset_crop(crops.crops["spring_wheat"])
    # Verify pools persisted
    assert (
        orch.micro_state.zn_total[0] > 60.0
    ), "Zn total should reflect amendment from season 1"
    assert (
        orch.micro_state.zn_available[0] > 0.5
    ), "Zn available should persist across seasons"


def test_high_ph_reduces_fe_availability() -> None:
    """Running simulation at high pH should reduce Fe availability.

    Ref: Lindsay 1979 — Fe solubility drops 1000x per pH unit above 7.
    """
    bus = EventBus()
    state = MicronutrientState.from_layers(1)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), 1)
    # Simulate pH change
    cycle._ph_by_layer[0] = 8.0
    for _ in range(30):
        cycle.daily_step(biomass_inc_g_m2=0.0)
    assert (
        state.fe_available[0] < 8.0
    ), f"Fe at pH 8.0 should be < 8 ppm, got {state.fe_available[0]:.1f}"
