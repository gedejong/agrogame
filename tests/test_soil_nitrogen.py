from __future__ import annotations

from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.water.events import WaterDrained
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
    cycle = NitrogenCycle(bus, state)

    # Capture nitrogen events
    nitrif = []
    leached = []
    bus.subscribe(NitrificationOccurred, lambda e: nitrif.append(e))
    bus.subscribe(NutrientLeached, lambda e: leached.append(e))

    # Trigger drainage from layer 0 to below profile to cause leaching
    bus.emit(WaterDrained(from_layer=0, to_layer=999, amount_mm=10.0))

    # Some NO3 should be reduced in layer 0 and a leaching event emitted
    assert state.no3[0] < 30.0
    assert any(ev.nutrient == "NO3" for ev in leached)

    # Run a daily step; should create a nitrification event given NH4 > 0
    fluxes = cycle.daily_step(temperature_c=20.0, moisture_rel=1.0)

    assert fluxes.nitrified_kg_ha >= 0.0
    assert len(nitrif) >= 1
