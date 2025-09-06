from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.microbes.biomass import (
    MicrobialBiomassModule,
    MicrobialParams,
)
from agrogame.soil.microbes.events import SubstrateAvailable, RhizospherePrimingPulse


def test_monod_growth_increases_with_substrate() -> None:
    bus = EventBus()
    mod = MicrobialBiomassModule(MicrobialParams(n_layers=1), event_bus=bus)

    # No substrate event: uses default available (~2.0)
    before = mod.state.layers[0].c_kg_ha
    mod.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])
    mid = mod.state.layers[0].c_kg_ha

    # Higher substrate should lead to more growth
    bus.emit(SubstrateAvailable(layer=0, available_c_kg_ha=10.0, quality_index=1.0))
    mod.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])
    after = mod.state.layers[0].c_kg_ha

    assert after - mid > mid - before


def test_priming_multiplier_scales_activity() -> None:
    # Compare two identical modules from the same starting state,
    # one with priming pulse and one without.
    params = MicrobialParams(n_layers=1)

    bus_a = EventBus()
    mod_a = MicrobialBiomassModule(params, event_bus=bus_a)
    bus_a.emit(SubstrateAvailable(layer=0, available_c_kg_ha=2.0, quality_index=0.8))
    mod_a.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])
    c_a = mod_a.state.layers[0].c_kg_ha

    bus_b = EventBus()
    mod_b = MicrobialBiomassModule(params, event_bus=bus_b)
    bus_b.emit(RhizospherePrimingPulse(layer=0, multiplier=2.0))
    bus_b.emit(SubstrateAvailable(layer=0, available_c_kg_ha=2.0, quality_index=0.8))
    mod_b.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])
    c_b = mod_b.state.layers[0].c_kg_ha

    # primed module should end with higher C after one day
    assert c_b > c_a
