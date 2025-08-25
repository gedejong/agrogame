from __future__ import annotations

from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.water.events import WaterDrained
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.nitrogen import (
    NitrogenCycle,
    SoilNitrogenState,
    NitrificationOccurred,
    NutrientLeached,
)


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
            initial_no3_kg_ha=30.0,
            initial_nh4_kg_ha=5.0,
            initial_p_kg_ha=10.0,
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


def test_nitrogen_event_wiring_and_daily_step():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    water = SoilWaterState(profile)
    cycle = NitrogenCycle(bus, state, water_state=water, profile=profile)

    # Capture nitrogen events
    nitrif = []
    leached = []
    bus.subscribe(NitrificationOccurred, lambda e: nitrif.append(e))
    bus.subscribe(NutrientLeached, lambda e: leached.append(e))

    # Compute initial storage to infer movement fraction
    storage0 = water.layer_storage_mm(profile, 0)
    bus.emit(WaterDrained(from_layer=0, to_layer=999, amount_mm=storage0 * 0.1))

    # Some NO3 should be reduced in layer 0 and a leaching event emitted
    assert state.no3[0] < 30.0
    assert any(ev.nutrient == "NO3" for ev in leached)

    # Run a daily step; should create a nitrification event given NH4 > 0
    fluxes = cycle.daily_step(temperature_c=20.0)

    assert fluxes.nitrified_kg_ha >= 0.0
    assert len(nitrif) >= 1


def test_nitrification_depends_on_temperature_and_ph():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    state.nh4[0] = 10.0
    water = SoilWaterState(profile)
    cycle = NitrogenCycle(bus, state, water_state=water, profile=profile)

    # Low temperature and acidic pH reduce nitrification
    flux_cold_acid = cycle.daily_step(temperature_c=5.0, ph_by_layer=[5.0, 7.0, 7.0])

    # Higher temperature and neutral pH increase nitrification
    state.nh4[0] = 10.0
    flux_warm_neutral = cycle.daily_step(
        temperature_c=25.0, ph_by_layer=[7.0, 7.0, 7.0]
    )

    assert flux_warm_neutral.nitrified_kg_ha > flux_cold_acid.nitrified_kg_ha


def test_denitrification_under_anaerobic_conditions():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    state.no3[0] = 20.0
    water = SoilWaterState(profile)
    # Force near-saturation to trigger anaerobic factor
    water.theta[0] = profile.layers[0].saturation
    cycle = NitrogenCycle(bus, state, water_state=water, profile=profile)

    flux = cycle.daily_step(temperature_c=25.0)
    assert flux.denitrified_kg_ha > 0.0


def test_plant_uptake_allocation_by_roots():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    state.no3 = [10.0, 10.0, 10.0]
    state.nh4 = [0.0, 0.0, 0.0]
    water = SoilWaterState(profile)
    cycle = NitrogenCycle(bus, state, water_state=water, profile=profile)

    root_fracs = [0.6, 0.3, 0.1]
    demand = 6.0
    _ = cycle.daily_step(
        temperature_c=20.0, plant_demand_kg_ha=demand, root_fractions=root_fracs
    )
    # Top layer should lose more than lower layers according to root fractions
    assert state.no3[0] < state.no3[1]
    assert state.no3[0] < state.no3[2]


def test_fertilizer_application_updates_pools():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    water = SoilWaterState(profile)
    cycle = NitrogenCycle(bus, state, water_state=water, profile=profile)

    cycle.apply_urea(layer=0, amount_kg_ha=20.0)
    assert state.nh4[0] >= 20.0

    cycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=10.0)
    assert (
        state.nh4[0] >= 25.0
        and state.no3[0] >= profile.layers[0].initial_no3_kg_ha + 5.0
    )


def test_within_profile_leaching_transfers_no3_downward():
    profile = make_profile()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    state.no3[0] = 40.0
    state.no3[1] = 0.0
    water = SoilWaterState(profile)
    _ = NitrogenCycle(bus, state, water_state=water, profile=profile)

    storage0 = water.layer_storage_mm(profile, 0)
    # Drain 50% of storage from layer 0 to layer 1
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=0.5 * storage0))

    # About 50% of NO3 should have moved from layer 0 to 1
    assert 15.0 <= state.no3[1] <= 25.0
    assert 15.0 <= state.no3[0] <= 25.0
