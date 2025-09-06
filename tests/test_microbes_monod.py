from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.microbes.biomass import (
    MicrobialBiomassModule,
    MicrobialParams,
)
from agrogame.soil.microbes.events import (
    SubstrateAvailable,
    RhizospherePrimingPulse,
    MicrobialActivityComputed,
)


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
    # Compare emitted activity index with and without priming pulse
    params = MicrobialParams(n_layers=1)

    last_activity_a = 0.0
    bus_a = EventBus()

    def _on_act_a(ev: MicrobialActivityComputed) -> None:
        nonlocal last_activity_a
        last_activity_a = float(ev.activity_index)

    bus_a.subscribe(MicrobialActivityComputed, _on_act_a)
    mod_a = MicrobialBiomassModule(params, event_bus=bus_a)
    bus_a.emit(SubstrateAvailable(layer=0, available_c_kg_ha=2.0, quality_index=0.8))
    mod_a.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])

    last_activity_b = 0.0
    bus_b = EventBus()

    def _on_act_b(ev: MicrobialActivityComputed) -> None:
        nonlocal last_activity_b
        last_activity_b = float(ev.activity_index)

    bus_b.subscribe(MicrobialActivityComputed, _on_act_b)
    mod_b = MicrobialBiomassModule(params, event_bus=bus_b)
    bus_b.emit(RhizospherePrimingPulse(layer=0, multiplier=2.0))
    bus_b.emit(SubstrateAvailable(layer=0, available_c_kg_ha=2.0, quality_index=0.8))
    mod_b.daily_step_layers(temperature_c=20.0, wfps_by_layer=[0.6], ph_by_layer=[6.8])

    assert last_activity_b > last_activity_a
