"""Tests covering missing lines in agrogame/soil/nitrogen/cycle.py."""

from __future__ import annotations

from pathlib import Path


from agrogame.events import EventBus
import agrogame.sim  # noqa: F401 — resolve circular import
from agrogame.soil.nitrogen import NitrogenCycle, SoilNitrogenState
from agrogame.soil.water.events import WaterDrained, TranspirationByLayer
from agrogame.soil.loader import load_soil_presets


def _make_cycle(
    no3: list[float] | None = None,
    nh4: list[float] | None = None,
    organic_n: list[float] | None = None,
) -> tuple[NitrogenCycle, EventBus]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    bus = EventBus()
    state = SoilNitrogenState(profile)
    n = len(state.no3)
    if no3 is not None:
        state.no3 = no3[:n] + [0.0] * max(0, n - len(no3))
    if nh4 is not None:
        state.nh4 = nh4[:n] + [0.0] * max(0, n - len(nh4))
    if organic_n is not None:
        state.organic_n = organic_n[:n] + [0.0] * max(0, n - len(organic_n))
    cycle = NitrogenCycle(bus, state)
    return cycle, bus


# ---------------------------------------------------------------------------
# _on_water_drained — various guard-clause paths
# ---------------------------------------------------------------------------


def test_drain_from_invalid_layer() -> None:
    """Cover line 95: from_layer out of range."""
    cycle, bus = _make_cycle()
    orig = list(cycle.state.no3)
    bus.emit(WaterDrained(from_layer=99, to_layer=1, amount_mm=5.0))
    assert cycle.state.no3 == orig


def test_drain_zero_amount() -> None:
    """Cover line 99/103: amount_mm 0 -> fraction 0."""
    cycle, bus = _make_cycle()
    orig = list(cycle.state.no3)
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=0.0))
    assert cycle.state.no3 == orig


def test_drain_negative_amount() -> None:
    """Cover line 103: negative amount -> fraction clamped to 0."""
    cycle, bus = _make_cycle()
    orig = list(cycle.state.no3)
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=-1.0))
    assert cycle.state.no3 == orig


def test_drain_zero_pool() -> None:
    """Cover line 108: moved <= 0 because pool is 0."""
    cycle, bus = _make_cycle(no3=[0.0, 10.0, 10.0])
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=5.0))
    assert cycle.state.no3[0] == 0.0


def test_drain_leaches_beyond_profile() -> None:
    """Cover line 134 and 136: to_layer >= n_layers -> NutrientLeached."""
    cycle, bus = _make_cycle(no3=[10.0, 10.0, 10.0])
    n = len(cycle.state.no3)
    captured = []
    from agrogame.soil.nitrogen.events import NutrientLeached

    bus.subscribe(NutrientLeached, lambda e: captured.append(e))
    bus.emit(WaterDrained(from_layer=n - 1, to_layer=n, amount_mm=50.0))
    assert len(captured) == 1
    assert captured[0].nutrient == "NO3"


def test_drain_moves_to_valid_layer() -> None:
    """Cover normal drain to valid layer."""
    cycle, bus = _make_cycle(no3=[10.0, 0.0, 0.0])
    bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=50.0))
    assert cycle.state.no3[0] < 10.0
    assert cycle.state.no3[1] > 0.0


# ---------------------------------------------------------------------------
# _on_transpiration_by_layer paths
# ---------------------------------------------------------------------------


def test_transpiration_no_profile() -> None:
    """Cover line 134: profile is None early return."""
    cycle, bus = _make_cycle()
    bus.emit(TranspirationByLayer(layer_indices=(0,), amounts_mm=(1.0,), total_mm=1.0))


def test_transpiration_empty_layers() -> None:
    """Cover line 136: empty layer_indices."""
    cycle, bus = _make_cycle()
    bus.emit(TranspirationByLayer(layer_indices=(), amounts_mm=(), total_mm=0.0))


# ---------------------------------------------------------------------------
# daily_step with various conditions
# ---------------------------------------------------------------------------


def test_daily_step_basic() -> None:
    """Cover mineralization, nitrification, denitrification paths."""
    cycle, _ = _make_cycle(
        no3=[10.0, 10.0, 10.0],
        nh4=[20.0, 20.0, 20.0],
        organic_n=[100.0, 100.0, 100.0],
    )
    fluxes = cycle.daily_step(
        temperature_c=25.0,
        plant_demand_kg_ha=5.0,
        ph_by_layer=[6.5] * len(cycle.state.no3),
    )
    assert fluxes.mineralized_kg_ha >= 0.0
    assert fluxes.nitrified_kg_ha >= 0.0
    assert fluxes.plant_uptake_kg_ha >= 0.0


def test_daily_step_zero_organic_n() -> None:
    """Cover line 315: organic_n is 0 -> mineralization returns 0."""
    cycle, _ = _make_cycle(organic_n=[0.0] * 10)
    fluxes = cycle.daily_step(temperature_c=20.0)
    assert fluxes.mineralized_kg_ha == 0.0


def test_daily_step_zero_nh4() -> None:
    """Cover line 336: nh4 is 0 and organic_n is 0 -> nitrification returns 0."""
    cycle, _ = _make_cycle(nh4=[0.0] * 10, organic_n=[0.0] * 10)
    fluxes = cycle.daily_step(temperature_c=20.0)
    assert fluxes.nitrified_kg_ha == 0.0


def test_daily_step_zero_no3() -> None:
    """Cover line 369: no3 is 0 -> denitrification returns 0."""
    cycle, _ = _make_cycle(no3=[0.0] * 10)
    fluxes = cycle.daily_step(temperature_c=20.0)
    assert fluxes.denitrified_kg_ha == 0.0


def test_daily_step_low_ph() -> None:
    """Cover pH factor edge: low pH gives 0 nitrification."""
    cycle, _ = _make_cycle()
    n = len(cycle.state.no3)
    fluxes = cycle.daily_step(temperature_c=20.0, ph_by_layer=[3.0] * n)
    assert fluxes.nitrified_kg_ha == 0.0


def test_daily_step_high_ph() -> None:
    """Cover pH factor edge: high pH gives 0 nitrification."""
    cycle, _ = _make_cycle()
    n = len(cycle.state.no3)
    fluxes = cycle.daily_step(temperature_c=20.0, ph_by_layer=[9.5] * n)
    assert fluxes.nitrified_kg_ha == 0.0


def test_daily_step_with_root_fractions_cached() -> None:
    """Cover cached root fractions path."""
    cycle, bus = _make_cycle()
    from agrogame.plant.roots.events import RootDistributionUpdated

    n = len(cycle.state.no3)
    fracs = [1.0 / n] * n
    bus.emit(RootDistributionUpdated(fractions=tuple(fracs)))
    fluxes = cycle.daily_step(temperature_c=20.0, plant_demand_kg_ha=5.0)
    assert fluxes.plant_uptake_kg_ha > 0.0
