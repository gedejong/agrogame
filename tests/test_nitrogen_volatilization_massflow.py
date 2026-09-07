"""NH3 volatilisation confined to exposed surface fertiliser; mass flow as a diagnostic.

Field losses: surface urea loses 10-30 % of its N as NH3, ammonium nitrate 1-3 %
(Bouwman, Boumans & Batjes 2002) and unfertilised soil a trace, because the NH3
share of ammoniacal N at bulk soil pH is ~1 % of its value in the pH ~9 urea
band (Sommer, Schjoerring & Denmead 2004). Transpiration mass flow is reported,
not debited: plant uptake is demand-driven and availability-capped (ADR-013).
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any, cast

import pytest

from agrogame.events import EventBus
from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.nitrogen import (
    MassFlowNSupplyComputed,
    NitrogenCycle,
    NitrogenRateParams,
    SoilNitrogenState,
    VolatilizationOccurred,
)
from agrogame.soil.water.events import TranspirationByLayer
from agrogame.soil.water.state import SoilWaterState

N_LAYERS = 3
# pH 4 switches nitrification off (pH factor 0), so a change in surface NH4 is
# volatilisation alone; pH 6.8 is the bulk-soil default.
ACID = [4.0] * N_LAYERS
NEUTRAL = [6.8] * N_LAYERS


def _profile() -> SoilProfile:
    layer: dict[str, Any] = {
        "depth_cm": 40,
        "texture": "loam",
        "field_capacity": 0.30,
        "wilting_point": 0.12,
        "saturation": 0.45,
        "bulk_density_g_cm3": 1.3,
        "ksat_mm_per_hour": 20,
        "organic_matter_pct": 3.0,
        "initial_no3_kg_ha": 30.0,
        "initial_nh4_kg_ha": 15.0,
        "initial_p_kg_ha": 25.0,
    }
    return SoilProfile(
        name="loam-test", layers=[SoilLayer(**layer) for _ in range(N_LAYERS)]
    )


def _cycle(
    nh4_top: float, params: NitrogenRateParams | None = None
) -> tuple[NitrogenCycle, SoilNitrogenState]:
    """A cycle without organic N so that mineralisation cannot mask surface fluxes."""
    profile = _profile()
    state = SoilNitrogenState(profile)
    state.organic_n = [0.0] * N_LAYERS
    state.nh4 = [nh4_top, 0.0, 0.0]
    cycle = NitrogenCycle(EventBus(), state, profile=cast(Any, profile), params=params)
    return cycle, state


def _day_loss(cycle: NitrogenCycle, state: SoilNitrogenState, ph: list[float]) -> float:
    before = state.nh4[0]
    cycle.daily_step(temperature_c=20.0, ph_by_layer=ph)
    return before - state.nh4[0]


def _volatilised(cycle: NitrogenCycle, ph: list[float], days: int) -> float:
    seen: list[float] = []
    cycle.event_bus.subscribe(
        VolatilizationOccurred, lambda ev: seen.append(ev.amount_kg_ha)
    )
    for _ in range(days):
        cycle.daily_step(temperature_c=20.0, ph_by_layer=ph)
    return sum(seen)


# --- volatilisation ---------------------------------------------------------


def test_unfertilised_topsoil_loses_a_trace() -> None:
    cycle, state = _cycle(nh4_top=20.0)
    loss = _day_loss(cycle, state, ACID)
    assert 0.0 < loss / 20.0 < 0.001


def test_native_loss_follows_the_nh3_fraction_at_soil_ph() -> None:
    # 20 kg NH4 at pH 6.8: 5 %/d x (NH3 share 0.35 % / 36 % in the urea band)
    # ~ 0.01 kg/d before same-day nitrification trims the pool a little.
    cycle, _ = _cycle(nh4_top=20.0)
    neutral = _volatilised(cycle, NEUTRAL, days=1)
    cycle, _ = _cycle(nh4_top=20.0)
    acid = _volatilised(cycle, ACID, days=1)
    assert 0.005 < neutral < 0.015
    assert acid < 1e-4


def test_surface_urea_loses_the_base_rate_then_a_quarter_in_total() -> None:
    cycle, state = _cycle(nh4_top=0.0)
    cycle.apply_urea(0, 100.0)
    assert state.surface_fertilizer_nh4_kg_ha == 100.0
    losses = [_day_loss(cycle, state, ACID) for _ in range(40)]
    # 5 %/d base rate at 20 degC (Q10 factor 1) on the freshly applied band
    assert losses[0] == pytest.approx(5.0)
    # cumulative loss inside the 10-30 % field range, centred near 25 %
    assert 22.0 <= sum(losses) <= 28.0
    # the exposed pool decays monotonically and is incorporated by then
    assert all(a >= b for a, b in pairwise(losses))
    assert state.surface_fertilizer_nh4_kg_ha < 0.1


def test_faster_incorporation_lowers_cumulative_urea_loss() -> None:
    fast = NitrogenRateParams(fertilizer_incorporation_rate_per_day=0.5)
    cycle_default, _ = _cycle(nh4_top=0.0)
    cycle_default.apply_urea(0, 100.0)
    cycle_fast, _ = _cycle(nh4_top=0.0, params=fast)
    cycle_fast.apply_urea(0, 100.0)
    default_total = _volatilised(cycle_default, ACID, days=30)
    fast_total = _volatilised(cycle_fast, ACID, days=30)
    assert fast_total < default_total
    # incorporation 0.5/d with loss 0.05/d: geometric sum 5 / (1 - 0.475) ~ 9.5 kg
    assert 9.0 < fast_total < 10.0


def test_ammonium_nitrate_is_not_exposed() -> None:
    cycle, state = _cycle(nh4_top=0.0)
    no3_before = state.no3[0]
    cycle.apply_ammonium_nitrate(0, 100.0)
    assert state.surface_fertilizer_nh4_kg_ha == 0.0
    assert state.nh4[0] == 50.0
    assert state.no3[0] == no3_before + 50.0
    assert _day_loss(cycle, state, ACID) < 0.01


def test_deep_urea_placement_is_incorporated() -> None:
    cycle, state = _cycle(nh4_top=0.0)
    cycle.apply_urea(1, 100.0)
    assert state.nh4[1] == 100.0
    assert state.surface_fertilizer_nh4_kg_ha == 0.0


def test_exposed_pool_never_exceeds_topsoil_nh4() -> None:
    cycle, state = _cycle(nh4_top=0.0)
    cycle.apply_urea(0, 100.0)
    for _ in range(30):
        cycle.daily_step(temperature_c=25.0, ph_by_layer=[7.0] * N_LAYERS)
        assert 0.0 <= state.surface_fertilizer_nh4_kg_ha <= state.nh4[0] + 1e-9


def test_volatilisation_events_match_the_pool_change() -> None:
    cycle, state = _cycle(nh4_top=10.0)
    cycle.apply_urea(0, 50.0)
    before = state.nh4[0]
    emitted = _volatilised(cycle, ACID, days=10)
    assert emitted == pytest.approx(before - state.nh4[0])


def test_temperature_scaled_rate_is_capped() -> None:
    # 40 degC gives a Q10 factor of 4 on the 5 %/d base rate; the cap holds the
    # realised rate at 10 %/d.
    cycle, state = _cycle(nh4_top=0.0)
    cycle.apply_urea(0, 100.0)
    before = state.nh4[0]
    cycle.daily_step(temperature_c=40.0, ph_by_layer=ACID)
    assert before - state.nh4[0] == pytest.approx(10.0)


# --- mass flow ------------------------------------------------------------------


def test_mass_flow_is_a_diagnostic() -> None:
    profile = _profile()
    state = SoilNitrogenState(profile)
    bus = EventBus()
    water = SoilWaterState(profile)
    cycle = NitrogenCycle(
        bus, state, water_state=cast(Any, water), profile=cast(Any, profile)
    )
    seen: list[MassFlowNSupplyComputed] = []
    bus.subscribe(MassFlowNSupplyComputed, seen.append)
    no3_before = list(state.no3)

    bus.emit(
        TranspirationByLayer(layer_indices=(0, 1), amounts_mm=(3.0, 1.0), total_mm=4.0)
    )

    assert state.no3 == no3_before
    assert len(seen) == 1
    expected = [
        min(no3_before[i], no3_before[i] / water.layer_storage_mm(profile, i) * take)
        for i, take in ((0, 3.0), (1, 1.0))
    ] + [0.0]
    assert seen[0].by_layer == pytest.approx(tuple(expected))
    assert seen[0].total_kg_ha == pytest.approx(sum(expected))
    assert cycle.massflow_supply_kg_ha == pytest.approx(sum(expected))
    assert seen[0].total_kg_ha > 0.0


def test_mass_flow_without_water_state_is_silent() -> None:
    cycle, state = _cycle(nh4_top=0.0)
    seen: list[MassFlowNSupplyComputed] = []
    cycle.event_bus.subscribe(MassFlowNSupplyComputed, seen.append)
    cycle.event_bus.emit(
        TranspirationByLayer(layer_indices=(0,), amounts_mm=(3.0,), total_mm=3.0)
    )
    assert seen == []
    assert cycle.massflow_supply_kg_ha == 0.0
    assert state.no3[0] == 30.0


# --- persistence --------------------------------------------------------------


def test_snapshot_round_trips_the_exposed_pool() -> None:
    from agrogame.sim.orchestrator import SoilSnapshot

    snap = SoilSnapshot(n_surface_fertilizer_nh4=12.5)
    assert SoilSnapshot.from_dict(snap.to_dict()).n_surface_fertilizer_nh4 == 12.5
    # Saves written before the field existed restore with an empty exposed pool.
    legacy = snap.to_dict()
    del legacy["n_surface_fertilizer_nh4"]
    assert SoilSnapshot.from_dict(legacy).n_surface_fertilizer_nh4 == 0.0


def test_orchestrator_snapshot_restores_the_exposed_pool() -> None:
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.loader import load_soil_presets

    profile = load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile, event_bus=EventBus())
    orch.apply_fertilizer("urea", 60.0)
    snap = orch.snapshot_soil()
    assert snap.n_surface_fertilizer_nh4 == 60.0

    orch.n_state.surface_fertilizer_nh4_kg_ha = 0.0
    orch.restore_soil(snap)
    assert orch.n_state.surface_fertilizer_nh4_kg_ha == 60.0
