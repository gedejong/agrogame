from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.events import EventBus
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.water.state import SoilWaterState

from agrogame.soil.phosphorus import (
    PhosphorusCycle,
    SoilPhosphorusState,
    PhosphorusFixationOccurred,
)
from agrogame.soil.nitrogen import NutrientLeached

if TYPE_CHECKING:
    from agrogame.soil.phosphorus.cycle import (
        _WaterState as _PWaterState,
        _WaterProfile as _PWaterProfile,
    )
else:
    _PWaterState = Any
    _PWaterProfile = Any


def make_profile() -> SoilProfile:
    layers = [
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=3.0,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=15.0,
        ),
        SoilLayer(
            depth_cm=30,
            texture="loam",
            field_capacity=0.28,
            wilting_point=0.11,
            saturation=0.42,
            bulk_density_g_cm3=1.35,
            ksat_mm_per_hour=18,
            organic_matter_pct=2.0,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=1.5,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
    ]
    return SoilProfile(name="test", layers=layers)


def test_phosphorus_event_wiring_and_minimal_leaching() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    _ = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    leached = []
    bus.subscribe(NutrientLeached, lambda e: leached.append(e))

    storage0 = water.layer_storage_mm(profile, 0)
    # Leaching only when very heavy drainage
    bus.emit(WaterDrained(from_layer=0, to_layer=999, amount_mm=storage0 * 0.9))

    # Tiny loss should occur
    assert state.available_p[0] < profile.layers[0].initial_p_kg_ha
    assert any(ev.nutrient == "P" for ev in leached)


def test_daily_step_emits_fixation_and_respects_ph() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    fix_events = []
    bus.subscribe(PhosphorusFixationOccurred, lambda e: fix_events.append(e))

    # Acidic pH triggers more fixation
    flux_acid = cycle.daily_step(temperature_c=25.0, ph_by_layer=[5.0, 7.0, 7.0])

    # Reset and test neutral pH yields less fixation
    state.available_p = [15.0, 0.0, 0.0]
    flux_neutral = cycle.daily_step(temperature_c=25.0, ph_by_layer=[7.0, 7.0, 7.0])

    assert flux_acid.fixed_kg_ha >= flux_neutral.fixed_kg_ha
    assert len(fix_events) >= 1


def test_uptake_uses_root_fractions_and_ph_availability() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    # Demand focused on top layer with acidic pH reduces effective uptake
    root_fracs = [0.8, 0.15, 0.05]
    flux_acid = cycle.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=5.0,
        root_fractions=root_fracs,
        ph_by_layer=[5.0, 7.0, 7.0],
    )

    # Reset with a fresh state to avoid prior-day side effects on OM pool
    state2 = SoilPhosphorusState(profile)
    state2.available_p = [15.0, 0.0, 0.0]
    cycle2 = PhosphorusCycle(
        bus,
        state2,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )
    flux_neutral = cycle2.daily_step(
        temperature_c=20.0,
        plant_demand_kg_ha=5.0,
        root_fractions=root_fracs,
        ph_by_layer=[7.0, 7.0, 7.0],
    )

    assert flux_neutral.plant_uptake_kg_ha >= flux_acid.plant_uptake_kg_ha


def test_fertilizer_apis_increase_available_p() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    base = list(state.available_p)
    cycle.apply_triple_superphosphate(layer=0, amount_kg_ha=10.0)
    assert state.available_p[0] >= base[0] + 10.0

    before = state.available_p[0]
    cycle.apply_slow_release_p(layer=0, amount_kg_ha=20.0, release_days=30)
    # Immediate fraction of slow-release applied
    assert state.available_p[0] >= before + 4.0


def test_slow_release_schedule_releases_full_amount_over_days() -> None:
    # Build a profile with zero organic matter to avoid mineralization confounding
    layers = [
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=0.0,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
        SoilLayer(
            depth_cm=30,
            texture="loam",
            field_capacity=0.28,
            wilting_point=0.11,
            saturation=0.42,
            bulk_density_g_cm3=1.35,
            ksat_mm_per_hour=18,
            organic_matter_pct=0.0,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=0.0,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
    ]
    profile = SoilProfile(name="slow-release", layers=layers)
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    baseline_total = state.total_phosphorus_kg_ha()

    # Apply 20 kg/ha slow-release over 5 days → 4 immediate + 16 scheduled
    cycle.apply_slow_release_p(layer=0, amount_kg_ha=20.0, release_days=5)

    # Advance 5 days with neutral pH to minimize fixation rate
    for _ in range(5):
        cycle.daily_step(
            temperature_c=20.0, plant_demand_kg_ha=0.0, ph_by_layer=[7.0, 7.0, 7.0]
        )

    # After full release period, total P in the profile should have increased by ~20
    # (accounting for fixation moving within pools but preserving mass)
    total_after = state.total_phosphorus_kg_ha()
    assert total_after == baseline_total + 20.0


def test_temperature_sensitivity_increases_mineralization() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    # Lower temperature should mineralize less than higher temperature
    cold = cycle.daily_step(
        temperature_c=10.0, plant_demand_kg_ha=0.0, ph_by_layer=[7.0, 7.0, 7.0]
    )
    warm = cycle.daily_step(
        temperature_c=25.0, plant_demand_kg_ha=0.0, ph_by_layer=[7.0, 7.0, 7.0]
    )
    assert warm.mineralized_kg_ha > cold.mineralized_kg_ha


def test_mass_balance_conserved_without_inputs_or_outputs() -> None:
    profile = make_profile()
    bus = EventBus()
    state = SoilPhosphorusState(profile)
    water = SoilWaterState(profile)
    cycle = PhosphorusCycle(
        bus,
        state,
        water_state=cast(_PWaterState, water),
        profile=cast(_PWaterProfile, profile),
    )

    total_before = state.total_phosphorus_kg_ha()
    _ = cycle.daily_step(
        temperature_c=20.0, plant_demand_kg_ha=0.0, ph_by_layer=[7.0, 7.0, 7.0]
    )
    total_after = state.total_phosphorus_kg_ha()
    assert abs(total_after - total_before) < 1e-6
