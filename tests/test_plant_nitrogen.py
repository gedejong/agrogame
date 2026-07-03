"""Unit tests for the whole-shoot critical-N dilution model (#360).

Covers the critical-N curve, actual-N% / NNI, the documented NNI->stress
mapping, the stock-based demand, per-day accumulation, params validation, the
event runtime, and preset loading of the dilution coefficients.
"""

from __future__ import annotations

import math

import pytest

from agrogame.events import EventBus
from agrogame.plant.events import NutrientStressComputed, PlantNUptakeComputed
from agrogame.plant.nitrogen import (
    PlantNitrogenModule,
    PlantNitrogenParams,
    PlantNitrogenRuntime,
    PlantNitrogenState,
)

# Literature coefficients (see params.py for citations).
_MAIZE = PlantNitrogenParams(n_crit_a=3.40, n_crit_b=0.37)
_WHEAT = PlantNitrogenParams(n_crit_a=5.35, n_crit_b=0.442)


def test_critical_n_matches_literature_curves() -> None:
    """N_crit% = a*W^-b reproduces the maize/wheat source values."""
    maize = PlantNitrogenModule(_MAIZE)
    wheat = PlantNitrogenModule(_WHEAT)
    # Maize (Plénet & Lemaire): 3.40 * 5^-0.37 ~ 1.87% at 5 t/ha.
    assert math.isclose(maize.critical_n_pct(5.0), 3.40 * 5.0**-0.37, rel_tol=1e-9)
    assert 1.8 < maize.critical_n_pct(5.0) < 2.0
    # Wheat (Justes): 5.35 * 5^-0.442 ~ 2.63% at 5 t/ha.
    assert math.isclose(wheat.critical_n_pct(5.0), 5.35 * 5.0**-0.442, rel_tol=1e-9)
    assert 2.5 < wheat.critical_n_pct(5.0) < 2.8
    # Curve declines with biomass (dilution).
    assert maize.critical_n_pct(10.0) < maize.critical_n_pct(2.0)


def test_critical_n_flat_below_reference_biomass() -> None:
    """Below the reference biomass the curve is held flat (no W->0 blowup)."""
    m = PlantNitrogenModule(_MAIZE)
    at_ref = m.critical_n_pct(1.0)
    assert math.isclose(at_ref, 3.40, rel_tol=1e-9)  # a * 1^-b == a
    assert m.critical_n_pct(0.1) == at_ref
    assert m.critical_n_pct(0.0) == at_ref


def test_default_params_use_greenwood_fallback() -> None:
    """The default params are the documented generic-C3 fallback."""
    p = PlantNitrogenParams()
    assert math.isclose(p.n_crit_a, 5.70)
    assert math.isclose(p.n_crit_b, 0.50)


def test_actual_n_pct_and_nni() -> None:
    m = PlantNitrogenModule(_MAIZE)
    # 100 kg N/ha in 5000 kg/ha (500 g/m²) shoot DM -> 2.0% N.
    assert math.isclose(m.actual_n_pct(100.0, 5000.0), 2.0, rel_tol=1e-9)
    # NNI = actual / critical. shoot 500 g/m² = 5 t/ha.
    nni = m.nutrition_index(100.0, 500.0)
    assert math.isclose(nni, 2.0 / m.critical_n_pct(5.0), rel_tol=1e-9)
    assert nni > 1.0  # luxury


def test_nni_unstressed_for_near_zero_canopy() -> None:
    """A near-zero canopy is unstressed by definition (ratio ill-defined)."""
    m = PlantNitrogenModule(_MAIZE)
    assert m.nutrition_index(0.0, 0.0) == 1.0
    assert m.actual_n_pct(5.0, 0.0) == 0.0


def test_stress_mapping_clamp_luxury_and_floor() -> None:
    """Default mapping = clamp(NNI) with luxury cap and a small floor."""
    m = PlantNitrogenModule(_MAIZE)
    assert math.isclose(m.stress_from_nni(0.6), 0.6, rel_tol=1e-9)
    assert m.stress_from_nni(1.5) == 1.0  # luxury capped
    assert m.stress_from_nni(1.0) == 1.0
    assert m.stress_from_nni(0.0) == 0.05  # floor
    assert m.stress_from_nni(-1.0) == 0.05


def test_stress_mapping_linear_rescale() -> None:
    """Non-default anchors give the CERES-style linear NFAC rescale."""
    p = PlantNitrogenParams(
        n_crit_a=3.40,
        n_crit_b=0.37,
        nni_stress_min=0.2,
        nni_stress_ref=0.8,
        stress_floor=0.0,
    )
    m = PlantNitrogenModule(p)
    assert m.stress_from_nni(0.2) == 0.0
    assert m.stress_from_nni(0.8) == 1.0
    assert math.isclose(m.stress_from_nni(0.5), 0.5, rel_tol=1e-9)  # midpoint


def test_demand_to_critical_deficit() -> None:
    m = PlantNitrogenModule(_MAIZE)
    # shoot 500 g/m² = 5000 kg/ha, crit ~1.874% -> target ~93.7 kg/ha.
    target = 5000.0 * m.critical_n_pct(5.0) / 100.0
    assert math.isclose(m.demand_to_critical(500.0, 50.0), target - 50.0, rel_tol=1e-9)
    # No demand once stock exceeds target.
    assert m.demand_to_critical(500.0, target + 10.0) == 0.0
    # Near-zero canopy demands nothing.
    assert m.demand_to_critical(0.0, 0.0) == 0.0


def test_daily_step_accumulates_stock_and_records_diagnostics() -> None:
    m = PlantNitrogenModule(_MAIZE)
    state = PlantNitrogenState()
    # Two days of uptake into a 5 t/ha shoot.
    m.daily_step(state, uptake_kg_ha=40.0, shoot_dm_g_m2=500.0)
    m.daily_step(state, uptake_kg_ha=30.0, shoot_dm_g_m2=500.0)
    assert math.isclose(state.n_stock_kg_ha, 70.0, rel_tol=1e-9)
    assert math.isclose(state.actual_n_pct, 70.0 * 100.0 / 5000.0, rel_tol=1e-9)
    assert math.isclose(state.critical_n_pct, m.critical_n_pct(5.0), rel_tol=1e-9)
    assert math.isclose(
        state.nni, state.actual_n_pct / state.critical_n_pct, rel_tol=1e-9
    )
    assert 0.0 <= state.stress <= 1.0


def test_daily_step_graded_response_to_uptake() -> None:
    """More uptake at the same biomass yields strictly higher stress (graded)."""
    m = PlantNitrogenModule(_MAIZE)
    stresses = []
    for uptake in (10.0, 30.0, 60.0, 90.0):
        state = PlantNitrogenState()
        stresses.append(m.daily_step(state, uptake_kg_ha=uptake, shoot_dm_g_m2=500.0))
    assert stresses == sorted(stresses)
    assert stresses[0] < stresses[-1]
    # Not a bimodal 0/1 step — intermediate values are strictly between.
    assert 0.05 < stresses[1] < 1.0


def test_params_validation_rejects_bad_values() -> None:
    with pytest.raises(ValueError):
        PlantNitrogenParams(n_crit_a=0.0)
    with pytest.raises(ValueError):
        PlantNitrogenParams(n_crit_b=-0.1)
    with pytest.raises(ValueError):
        PlantNitrogenParams(reference_biomass_t_ha=0.0)
    with pytest.raises(ValueError):
        PlantNitrogenParams(nni_stress_min=1.0, nni_stress_ref=1.0)


def test_runtime_accumulates_and_emits_graded_stress() -> None:
    """Runtime consumes PlantNUptakeComputed and emits graded N stress."""
    bus = EventBus()
    module = PlantNitrogenModule(_MAIZE)
    state = PlantNitrogenState()
    shoot = {"g_m2": 500.0}
    PlantNitrogenRuntime(
        bus, module, state, shoot_biomass_provider=lambda: shoot["g_m2"]
    )
    emitted: list[NutrientStressComputed] = []
    bus.subscribe(NutrientStressComputed, emitted.append)

    bus.emit(PlantNUptakeComputed(uptake_kg_ha=30.0, demand_kg_ha=40.0))
    bus.emit(PlantNUptakeComputed(uptake_kg_ha=30.0, demand_kg_ha=40.0))

    assert math.isclose(state.n_stock_kg_ha, 60.0, rel_tol=1e-9)
    assert len(emitted) == 2
    assert all(e.nutrient == "N" for e in emitted)
    assert emitted[-1].demand_kg_ha == 40.0
    # Stress rose as the stock grew (graded, monotone).
    assert emitted[1].stress > emitted[0].stress


def test_presets_load_dilution_coefficients() -> None:
    """Maize/wheat carry fitted coefficients; other crops fall back to None."""
    from pathlib import Path

    from agrogame.plant.presets import load_crop_presets

    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    assert crops.crops["maize"].n_crit_a == 3.40
    assert crops.crops["maize"].n_crit_b == 0.37
    assert crops.crops["winter_wheat"].n_crit_a == 5.35
    assert crops.crops["spring_wheat"].n_crit_b == 0.442
    # A crop without a fitted curve uses the documented fallback (None here).
    assert crops.crops["sorghum"].n_crit_a is None
