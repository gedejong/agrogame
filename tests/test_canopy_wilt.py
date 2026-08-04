"""Graded drought leaf-senescence tests (#373).

The old wilt model removed a size-independent *fraction* (10%) of LAI in a
discrete step after N consecutive sub-threshold days. For a small, vigorously
growing canopy that fractional loss was swamped by growth from a low base, so
net LAI kept climbing through a severe drought ("drought never bites a small
canopy"). This module pins the replacement: a graded, per-unit-leaf daily
drought-senescence rate scaled by stress severity and modulated by live
rooting depth (FAO-56 TAW ∝ Zr; DSSAT CERES TURFAC; APSIM swdef_senescence).

The large-canopy wilt regression lives in
``tests/test_water_stress_feedback.py::test_wilt_damage_reduces_lai`` and is
intentionally left there.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.canopy.module import CanopyModule
from agrogame.soil.canopy.params import CanopyParams
from agrogame.soil.canopy.runtime import CanopyRuntime
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers


def _maize_orch() -> FullSimulationOrchestrator:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(profile, crop=crops.crops["maize"])
    # Adequate N so the canopy is water-limited, not N-limited (mirrors the
    # large-canopy regression). Isolates drought senescence.
    orch.apply_fertilizer("ammonium_nitrate", 200.0)
    return orch


def _run(
    orch: FullSimulationOrchestrator, n: int, rain: float, start: date, day0: int
) -> None:
    for i in range(day0, day0 + n):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rain),
            tmin_c=18.0,
            tmax_c=30.0,
            par_mj_m2=18.0,
            sim_date=start + timedelta(days=i),
        )


def _runtime() -> CanopyRuntime:
    p = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
    )
    return CanopyRuntime(event_bus=EventBus(), canopy=CanopyModule(p, EventBus()))


def _senesce_step(lai: float, depth_cm: float, stress: float) -> tuple[float, float]:
    """One graded-senescence step past the tolerance lag. Returns (rel, abs) loss."""
    rt = _runtime()
    rt._root_depth_cm = depth_cm
    rt.canopy.state.lai = lai
    rt._consecutive_wilt_days = rt.canopy.params.wilt_days_for_damage  # past the lag
    before = rt.canopy.state.lai
    rt._check_drought_senescence(stress)
    lost = before - rt.canopy.state.lai
    return lost / before, lost


# --------------------------------------------------------------------------- #
# Headline: the previously-missing small-canopy drought signal.
# --------------------------------------------------------------------------- #
def test_small_canopy_drought_is_materially_limited() -> None:
    """A small, growing canopy under drought must fall well below a watered control.

    This is the gap the old size-independent wilt step left open: net LAI of a
    small canopy climbed through drought because a fixed 10%-of-a-tiny-LAI step
    was swamped by growth. With graded per-unit-leaf senescence the drought
    trajectory sits far below the control in both LAI and biomass.
    """
    start = date(2024, 6, 1)

    # Build a genuinely small canopy (~8 days, LAI well below 0.5) then diverge.
    drought = _maize_orch()
    control = _maize_orch()
    _run(drought, 8, 6.0, start, 0)
    _run(control, 8, 6.0, start, 0)
    lai_pre = drought.canopy.state.lai
    assert lai_pre < 0.5, f"expected a small canopy, got LAI {lai_pre:.3f}"

    _run(drought, 30, 0.0, start, 8)  # total drought
    _run(control, 30, 6.0, start, 8)  # watered control

    lai_d = drought.canopy.state.lai
    lai_c = control.canopy.state.lai
    bio_d = drought.canopy.state.biomass_g_m2
    bio_c = control.canopy.state.biomass_g_m2

    # Control establishes a real canopy; drought is materially suppressed.
    assert lai_c > 4.0, f"watered control should build a canopy, got LAI {lai_c:.2f}"
    # Discriminating pin (#420): an ABSOLUTE drought-LAI bound that only the
    # graded per-unit-leaf model can meet. New graded model reproduces
    # lai_d ≈ 0.268 (passes with headroom); the old size-independent discrete
    # 10%-of-LAI step gives lai_d ≈ 1.505 and so FAILS this bound. The 0.5
    # threshold sits squarely between the two behaviours (0.268 < 0.5 < 1.505).
    assert lai_d < 0.5, (
        f"drought LAI ({lai_d:.3f}) must be materially limited in absolute terms "
        f"(new graded model ~0.268; old size-independent step ~1.505 fails this)"
    )
    # Relative asserts kept as sanity checks (they pass on both old and new, so
    # they are NOT the discriminating condition — the absolute pin above is).
    assert lai_d < 0.5 * lai_c, (
        f"drought LAI ({lai_d:.2f}) should sit far below control ({lai_c:.2f}) — "
        f"the small-canopy drought signal that was previously missing"
    )
    assert (
        bio_d < 0.6 * bio_c
    ), f"drought biomass ({bio_d:.1f}) should be well below control ({bio_c:.1f})"


# --------------------------------------------------------------------------- #
# Monotonicity: relative leaf-area loss must not shrink as the canopy shrinks.
# --------------------------------------------------------------------------- #
def test_relative_loss_not_smaller_for_small_canopy() -> None:
    """Per-unit-leaf senescence: relative loss is size-independent.

    The old inversion had a small canopy effectively lose less than a large one
    (its fractional step was overwhelmed by growth). A per-unit-leaf rate makes
    the *relative* loss equal for small and large canopies at equal stress and
    rooting depth — so it is never smaller for the small canopy. Absolute loss
    scales with LAI, as expected for a per-unit-leaf process.
    """
    small_rel, small_abs = _senesce_step(lai=0.3, depth_cm=40.0, stress=0.0)
    large_rel, large_abs = _senesce_step(lai=4.0, depth_cm=40.0, stress=0.0)

    assert small_rel > 0.0
    assert small_rel >= large_rel - 1e-9, (
        f"relative loss for a small canopy ({small_rel:.4f}) must not be smaller "
        f"than for a large one ({large_rel:.4f})"
    )
    # Per-unit-leaf: absolute loss tracks canopy size.
    assert large_abs > small_abs


def test_drought_senescence_is_graded_by_severity() -> None:
    """Deeper stress (lower Ta/Tp) senesces more leaf area — a graded response."""
    mild_rel, _ = _senesce_step(lai=3.0, depth_cm=40.0, stress=0.25)
    severe_rel, _ = _senesce_step(lai=3.0, depth_cm=40.0, stress=0.02)
    assert 0.0 < mild_rel < severe_rel


def test_no_senescence_above_onset_and_counter_resets() -> None:
    """Above the onset threshold no leaf is senesced and the stress lag resets."""
    rt = _runtime()
    rt.canopy.state.lai = 3.0
    rt._consecutive_wilt_days = 10
    rt._check_drought_senescence(0.5)  # above default onset 0.3
    assert rt.canopy.state.lai == 3.0
    assert rt._consecutive_wilt_days == 0


# --------------------------------------------------------------------------- #
# Rooting depth as an onset modifier (FAO-56 TAW ∝ Zr).
# --------------------------------------------------------------------------- #
def test_shallow_roots_senesce_more_than_deep() -> None:
    """Under identical drought, a shallow root profile senesces faster than deep.

    FAO-56: TAW ∝ rooting depth, so a shallow-rooted crop depletes its
    available water sooner and its leaves senesce more rapidly for the same
    Ta/Tp deficit (rapid seedling drought), while deep roots buffer it.
    """
    shallow_rel, _ = _senesce_step(lai=3.0, depth_cm=15.0, stress=0.05)
    deep_rel, _ = _senesce_step(lai=3.0, depth_cm=100.0, stress=0.05)
    assert shallow_rel > deep_rel


# --------------------------------------------------------------------------- #
# Statefulness across two drought cycles (counter reset + re-onset).
# --------------------------------------------------------------------------- #
def test_drought_senescence_bites_across_two_cycles() -> None:
    """Drought must knock LAI down in two separate droughts with recovery between.

    Exercises the stateful stress-lag counter: it must reset when the crop
    recovers and re-arm for a second drought, so the graded senescence fires in
    both cycles rather than latching or exhausting after the first.
    """
    start = date(2024, 6, 1)
    orch = _maize_orch()

    _run(orch, 25, 6.0, start, 0)
    lai_pre1 = orch.canopy.state.lai
    _run(orch, 18, 0.0, start, 25)  # drought 1
    lai_dr1 = orch.canopy.state.lai
    _run(orch, 20, 8.0, start, 43)  # recovery
    lai_pre2 = orch.canopy.state.lai
    _run(orch, 18, 0.0, start, 63)  # drought 2
    lai_dr2 = orch.canopy.state.lai

    # Discriminating pins (#420): ABSOLUTE penalties only the graded model meets.
    # Cycle-1 drought must remove > 1.0 LAI (new graded model removes ~1.49; the
    # old size-independent discrete step removes only ~0.42 and FAILS this).
    assert (lai_pre1 - lai_dr1) > 1.0, (
        f"cycle 1 drought must remove > 1.0 LAI in absolute terms "
        f"({lai_pre1:.2f} -> {lai_dr1:.2f}, removed {lai_pre1 - lai_dr1:.2f}; "
        f"new graded ~1.49, old step ~0.42 fails)"
    )
    assert lai_pre2 > lai_dr1, "canopy should recover between droughts"
    # Post-cycle-2 canopy must end materially suppressed (new ~0.999; old ~2.322).
    assert lai_dr2 < 1.5, (
        f"post-cycle-2 canopy must stay below 1.5 LAI "
        f"({lai_dr2:.3f}; new graded ~0.999, old step ~2.322 fails)"
    )
    assert (
        lai_dr2 < lai_pre2
    ), f"cycle 2 drought should reduce LAI again ({lai_pre2:.2f} -> {lai_dr2:.2f})"
