from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.chemistry import SoilChemistryModule
from agrogame.soil.chemistry.events import SoilPHUpdated
from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phosphorus import SoilPhosphorusState
from agrogame.soil.phosphorus.cycle import PhosphorusCycle


def _profile() -> SoilProfile:
    layers = [
        SoilLayer(
            depth_cm=30,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=2.0,
            initial_no3_kg_ha=10.0,
            initial_nh4_kg_ha=5.0,
            initial_p_kg_ha=10.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=1.2,
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
            organic_matter_pct=1.5,
            initial_no3_kg_ha=0.0,
            initial_nh4_kg_ha=0.0,
            initial_p_kg_ha=0.0,
        ),
    ]
    return SoilProfile(name="ph-test", layers=layers)


def test_ph_events_flow_into_n_and_p_cycles() -> None:
    profile = _profile()
    bus = EventBus()
    water = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    pstate = SoilPhosphorusState(profile)

    _ = NitrogenCycle(bus, nstate, water_state=water, profile=profile)
    _ = PhosphorusCycle(bus, pstate, water_state=water, profile=profile)

    chem = SoilChemistryModule(bus, n_layers=len(profile.layers), base_ph=7.0)

    # Collect pH events to ensure they are emitted
    seen: list[SoilPHUpdated] = []
    bus.subscribe(SoilPHUpdated, lambda e: seen.append(e))

    # Emit a daily buffering update and ensure handlers receive pH
    chem.daily_buffering(target_ph=5.5)
    assert seen, "Expected SoilPHUpdated events to be emitted"

    # Now run steps without explicitly passing pH; should use cached values
    _ = chem.ph_by_layer  # ensure property works
    # After acidifying, nitrification should be reduced vs neutral
    from copy import deepcopy

    # Snapshot
    nstate2 = deepcopy(nstate)
    # Step with acidic pH
    from agrogame.soil.nitrogen.cycle import NitrogenCycle as NC

    nc_acid = NC(bus, nstate2, water_state=water, profile=profile)
    flux_acid = nc_acid.daily_step(temperature_c=25.0)

    # Reset and set neutral pH via buffering then step
    chem.daily_buffering(target_ph=7.0)
    nstate3 = deepcopy(nstate)
    nc_neutral = NC(bus, nstate3, water_state=water, profile=profile)
    flux_neutral = nc_neutral.daily_step(temperature_c=25.0)

    assert (
        flux_neutral.nitrified_kg_ha >= flux_acid.nitrified_kg_ha
    ), "Nitrification should be higher at neutral pH"
