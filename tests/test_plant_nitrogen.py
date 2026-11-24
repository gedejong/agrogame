"""Unit tests for the whole-shoot critical-N dilution model (#360).

Covers the critical-N curve, actual-N% / NNI, the documented NNI->stress
mapping, the stock-based demand, per-day accumulation, params validation, the
event runtime, preset loading of the dilution coefficients, and the absence of
N uptake before emergence (#578).
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.params.phenology import PhenologyStage
from agrogame.plant.events import NutrientStressComputed, PlantNUptakeComputed
from agrogame.plant.nitrogen import (
    PlantNitrogenModule,
    PlantNitrogenParams,
    PlantNitrogenRuntime,
    PlantNitrogenState,
)
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator, _plant_n_params
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers

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


def test_wheat_preset_holds_justes_constant_below_1_55_t_ha() -> None:
    """Wheat holds N_ct = 4.4% below 1.55 t/ha (Justes et al. 1994, #603)."""
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    soils = load_soil_presets(Path("data/soils/presets.yaml"))
    for key in ("winter_wheat", "spring_wheat"):
        crop = crops.get_preset(key, "netherlands_temperate")
        assert crop.n_crit_reference_biomass_t_ha == 1.55
        orch = FullSimulationOrchestrator(
            soils.soils["loam_temperate"], crop=crop, latitude_deg=52.0
        )
        m = orch.plant_n_module
        assert math.isclose(m.critical_n_pct(1.55), 5.35 * 1.55**-0.442)
        assert abs(m.critical_n_pct(1.55) - 4.4) < 0.05
        for w in (0.0, 0.2, 1.0, 1.5):
            assert m.critical_n_pct(w) == m.critical_n_pct(1.55)
        assert m.critical_n_pct(1.6) < m.critical_n_pct(1.55)  # dilution resumes
        assert math.isclose(m.critical_n_pct(5.0), 5.35 * 5.0**-0.442)
    # Maize and the generic fallback keep the 1 t/ha threshold.
    assert crops.crops["maize"].n_crit_reference_biomass_t_ha is None
    maize = PlantNitrogenModule(_plant_n_params(crops.crops["maize"]))
    assert math.isclose(maize.critical_n_pct(0.5), 3.40)
    generic = PlantNitrogenModule(_plant_n_params(crops.crops["sorghum"]))
    assert math.isclose(generic.critical_n_pct(0.5), 5.70)


def test_wheat_threshold_survives_reset_crop_across_two_seasons() -> None:
    """The per-crop threshold is rebuilt on reset_crop and early NNI stays <= 1."""
    soils = load_soil_presets(Path("data/soils/presets.yaml"))
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "spring_wheat", "netherlands_temperate"
    )
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"], crop=crop, latitude_deg=52.0
    )
    for season, start in enumerate((date(2024, 4, 1), date(2025, 4, 1))):
        if season:
            orch.reset_crop(crop)
        assert orch.plant_n_module.params.reference_biomass_t_ha == 1.55
        _, nni = _run_de_bilt_april_cycle(orch, start)
        assert all(0.0 <= v <= 1.0 + 1e-9 for v in nni), f"season {season}"


# --- #578: no N uptake before emergence, no demand floor ---------------------

# De Bilt (KNMI station 260) April 1991-2020 means from etmgeg_260, tabulated in
# the #578 refinement: TN 4.52 °C, TX 14.84 °C, Q 14.14 MJ/m²/d (rounded to 14.0
# here). Rain is a constant 2.0 mm/day that keeps the seedbed moist.
_DE_BILT_APRIL_TMIN_C = 4.52
_DE_BILT_APRIL_TMAX_C = 14.84
_DE_BILT_APRIL_SHORTWAVE_MJ_M2 = 14.0
_DE_BILT_APRIL_RAIN_MM = 2.0
_DAYS_AFTER_EMERGENCE = 20
_MAX_DAYS = 60


def _nl_maize_orchestrator() -> FullSimulationOrchestrator:
    soils = load_soil_presets(Path("data/soils/presets.yaml"))
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", "netherlands_temperate"
    )
    return FullSimulationOrchestrator(
        soils.soils["loam_temperate"], crop=crop, latitude_deg=52.0
    )


def test_orchestrator_n_demand_has_no_floor() -> None:
    """Planted-crop N demand is exactly the deficit to critical (#578).

    2.0 g/m² of shoot DM is 20 kg/ha, below maize's 1 t/ha reference biomass,
    so critical N is the flat 3.40% (Plénet & Lemaire 1999): a 0.68 kg/ha
    target. A 0.6 kg/ha stock leaves a deficit of 0.08; a 0.7 kg/ha stock is
    above critical and demands nothing. The former ``max(0.1, ...)`` floor
    returned 0.1 for both.
    """
    orch = _nl_maize_orchestrator()
    orch.canopy.state.biomass_g_m2 = 2.0
    orch.plant_n_state.n_stock_kg_ha = 0.6
    assert math.isclose(orch._compute_plant_n_demand(), 0.08, rel_tol=1e-9)
    orch.plant_n_state.n_stock_kg_ha = 0.7
    assert orch._compute_plant_n_demand() == 0.0


def _run_de_bilt_april_cycle(
    orch: FullSimulationOrchestrator, start: date
) -> tuple[int, list[float]]:
    """Step to emergence + 20 days; return the emergence day and daily NNI.

    Asserts on the way that the shoot N stock is exactly 0.0 after every day up
    to and including the emergence day (AC3 b).
    """
    emergence_day: int | None = None
    nni: list[float] = []
    for day in range(1, _MAX_DAYS + 1):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=_DE_BILT_APRIL_RAIN_MM),
            tmin_c=_DE_BILT_APRIL_TMIN_C,
            tmax_c=_DE_BILT_APRIL_TMAX_C,
            shortwave_mj_m2=_DE_BILT_APRIL_SHORTWAVE_MJ_M2,
            sim_date=start + timedelta(days=day - 1),
        )
        nni.append(orch.plant_n_nni)
        if emergence_day is None:
            assert (
                orch.plant_n_stock_kg_ha == 0.0
            ), f"day {day}: {orch.plant_n_stock_kg_ha} kg N/ha banked pre-emergence"
            if orch.phenology.state.stage is not PhenologyStage.PLANTED:
                emergence_day = day
        elif day == emergence_day + _DAYS_AFTER_EMERGENCE:
            break
    assert emergence_day is not None, f"no emergence within {_MAX_DAYS} days"
    assert len(nni) == emergence_day + _DAYS_AFTER_EMERGENCE
    return emergence_day, nni


def test_no_n_banked_before_slow_emergence_across_two_cycles() -> None:
    """A slow, cool-spring emergence banks no N and spikes no NNI (#578).

    NL maize on ``loam_temperate`` under constant De Bilt April weather (KNMI
    station 260, 1991-2020 means; see the constants above) emerges on day 30.
    With the former 0.1 kg N/ha/day demand floor the stock reached 3.0 kg/ha by
    emergence and the first seedling day read NNI 29.26. No N is taken up
    before emergence in CERES-Maize or APSIM PMF, so the stock must be 0.0 then
    and NNI must not exceed 1 while the seedling's demand is the deficit to
    critical. A second season after ``reset_crop`` checks that the rebuilt
    plant-N state banks nothing either.
    """
    orch = _nl_maize_orchestrator()
    crop = orch._current_crop
    for season, start in enumerate((date(2024, 4, 1), date(2025, 4, 1))):
        if season:
            orch.reset_crop(crop)
        emergence_day, nni = _run_de_bilt_april_cycle(orch, start)
        assert 25 <= emergence_day <= 35, f"season {season}: day {emergence_day}"
        assert all(
            0.0 <= v <= 1.0 + 1e-9 for v in nni
        ), f"season {season}: max NNI {max(nni):.2f} (day {nni.index(max(nni)) + 1})"
        # The crop still takes N up after emergence and tracks critical.
        assert nni[-1] >= 0.9
        assert orch.plant_n_stock_kg_ha > 0.0
