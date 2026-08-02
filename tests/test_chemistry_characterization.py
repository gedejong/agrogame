"""Characterization tests for soil chemistry pH dynamics (#288).

Locks the numeric pH deltas, caps, and buffering behaviour that were
previously hard-coded (and ``# pragma: no cover``) in
``SoilChemistryModule``. These values must stay identical across the
canonical params/state/runtime refactor — this is a structural change with
no behaviour change.

Also exercises ``ChemistryRuntime`` so the event wiring (formerly on the
module) is covered.
"""

from __future__ import annotations

from datetime import date

import pytest

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.chemistry import (
    AcidifyingFertilizerApplied,
    ChemistryParams,
    ChemistryRuntime,
    ChemistryState,
    LimeApplied,
    SoilChemistryModule,
    SoilPHUpdated,
)
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.phosphorus.events import PhosphorusFixationOccurred

_ABS = 1e-12


def _module(
    bus: EventBus, base_ph: float = 6.8, n_layers: int = 2
) -> SoilChemistryModule:
    return SoilChemistryModule(
        ChemistryParams(),
        ChemistryState.from_layers(n_layers, base_ph=base_ph),
        bus,
    )


def test_default_params_match_legacy_constants() -> None:
    """Frozen params reproduce the previously hard-coded magic numbers."""
    p = ChemistryParams()
    assert p.base_ph == 6.8
    assert p.default_target_ph == 6.8
    assert p.buffering_rate == 0.001
    assert p.no3_leach_ph_delta == 0.005
    assert p.p_fixation_ph_delta == 0.002
    assert p.lime_ph_delta_per_kg_ha == 0.001
    assert p.acidifying_ph_delta_per_kg_ha == 0.0005
    assert p.ph_floor == 4.0
    assert p.ph_ceiling == 9.0


def test_daily_step_buffering_toward_target() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=7.0)
    chem.daily_step(target_ph=5.5)
    # 7.0 + 0.001 * (5.5 - 7.0) = 6.9985
    assert chem.ph_by_layer[0] == pytest.approx(6.9985, abs=_ABS)


def test_daily_step_defaults_to_param_target() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.0)
    chem.daily_step()  # target_ph None -> default_target_ph (6.8)
    # 6.0 + 0.001 * (6.8 - 6.0) = 6.0008
    assert chem.ph_by_layer[0] == pytest.approx(6.0008, abs=_ABS)


def test_lime_raises_ph_and_caps_at_ceiling() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.8)
    chem.apply_lime(0, 1000.0)  # +0.001 * 1000 = +1.0
    assert chem.ph_by_layer[0] == pytest.approx(7.8, abs=_ABS)
    chem.apply_lime(0, 5000.0)  # 7.8 + 5.0 -> capped at 9.0
    assert chem.ph_by_layer[0] == pytest.approx(9.0, abs=_ABS)


def test_acidifying_fertilizer_lowers_ph_and_floors() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.8)
    chem.apply_acidifying_fertilizer(0, 1000.0)  # -0.0005 * 1000 = -0.5
    assert chem.ph_by_layer[0] == pytest.approx(6.3, abs=_ABS)
    chem.apply_acidifying_fertilizer(0, 10000.0)  # 6.3 - 5.0 -> floored at 4.0
    assert chem.ph_by_layer[0] == pytest.approx(4.0, abs=_ABS)


def test_no3_leaching_acidifies_only_for_nitrate() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.8)
    chem.apply_nutrient_leaching("NO3", 0)  # -0.005
    assert chem.ph_by_layer[0] == pytest.approx(6.795, abs=_ABS)
    # Non-nitrate leaching leaves pH untouched.
    chem.apply_nutrient_leaching("NH4", 0)
    assert chem.ph_by_layer[0] == pytest.approx(6.795, abs=_ABS)


def test_no3_leaching_floors_at_ph_floor() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=4.002)
    chem.apply_nutrient_leaching("NO3", 0)  # 4.002 - 0.005 -> floored 4.0
    assert chem.ph_by_layer[0] == pytest.approx(4.0, abs=_ABS)


def test_phosphorus_fixation_acidifies() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.8)
    chem.apply_phosphorus_fixation(0)  # -0.002
    assert chem.ph_by_layer[0] == pytest.approx(6.798, abs=_ABS)


def test_set_state_restores_in_place() -> None:
    bus = EventBus()
    chem = _module(bus, base_ph=6.8)
    original_state = chem.state
    chem.set_state(ChemistryState(ph=[5.0, 5.5]))
    assert chem.ph_by_layer == [5.0, 5.5]
    # Same state object mutated in place (alias preserved).
    assert chem.state is original_state


def _tick(phase: str, target_ph: float | None = None) -> DayTick:
    return DayTick(sim_date=date(2024, 1, 1), phase=phase, target_ph=target_ph)


def test_runtime_dispatches_all_events() -> None:
    """ChemistryRuntime relocates the 5 subscriptions off the module."""
    bus = EventBus()
    chem = _module(bus, base_ph=6.8, n_layers=2)
    ChemistryRuntime(bus, chem)

    seen: list[SoilPHUpdated] = []
    bus.subscribe(SoilPHUpdated, seen.append)

    # DayTick on a non-chemistry phase is ignored (no buffering, no emit).
    bus.emit(_tick("water", target_ph=5.0))
    assert seen == []
    assert chem.ph_by_layer[0] == pytest.approx(6.8, abs=_ABS)

    # DayTick(chemistry) buffers toward the tick's target_ph.
    bus.emit(_tick("chemistry", target_ph=6.8))
    assert len(seen) == 2  # one SoilPHUpdated per layer
    assert chem.ph_by_layer[0] == pytest.approx(6.8, abs=_ABS)

    bus.emit(LimeApplied(layer=0, rate_kg_ha=1000.0))
    assert chem.ph_by_layer[0] == pytest.approx(7.8, abs=_ABS)

    bus.emit(AcidifyingFertilizerApplied(layer=1, rate_kg_ha=1000.0))
    assert chem.ph_by_layer[1] == pytest.approx(6.3, abs=_ABS)

    bus.emit(NutrientLeached(nutrient="NO3", amount_kg_ha=1.0, layer=0))
    assert chem.ph_by_layer[0] == pytest.approx(7.795, abs=_ABS)

    bus.emit(PhosphorusFixationOccurred(layer=1, amount_fixed_kg_ha=1.0))
    assert chem.ph_by_layer[1] == pytest.approx(6.298, abs=_ABS)
