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
            shortwave_mj_m2=18.0,
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
    # Re-baselined for ADR-014 (Phase 3d): under the corrected (halved) PAR
    # basis the watered control reaches LAI ~3.08 by day 38 (was >4 under the
    # 2×-inflated radiation), so the control pin drops 4.0 -> 2.8.
    assert lai_c > 2.8, f"watered control should build a canopy, got LAI {lai_c:.2f}"
    # Discriminating pin (#420): an ABSOLUTE drought-LAI bound that only the
    # graded per-unit-leaf model can meet. Re-derived for ADR-014: with the
    # smaller (halved-PAR) canopy transpiring less, this drought bites more
    # weakly, so the graded model settles at lai_d ≈ 0.957 (was ~0.268) while
    # the old size-independent discrete 10%-of-LAI step gives lai_d ≈ 1.437
    # (was ~1.505). The 1.2 threshold sits between the two behaviours
    # (0.957 < 1.2 < 1.437), preserving the #420 discrimination — re-verified by
    # temp-reverting to the old ``_check_wilt_damage`` step. (Was 0.5, which now
    # lies below both models and no longer discriminates.)
    assert lai_d < 1.2, (
        f"drought LAI ({lai_d:.3f}) must be materially limited in absolute terms "
        f"(new graded model ~0.957; old size-independent step ~1.437 fails this)"
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

    Re-derived for ADR-014 (Phase 3d). Under the corrected (halved) PAR basis
    the canopy transpires less and loam holds an ~8-day water buffer, so a
    *short* vegetative drought no longer drives Ta/Tp below the wilt onset for
    long enough to overcome concurrent growth — the pre-fix "18-day droughts on
    a 25-day canopy" scenario now sees LAI *climb* through both droughts, and
    (because graded senescence is severity-scaled) at the mild stress achievable
    here the graded model is actually *gentler* than the old fixed 10%-step,
    inverting the #420 contrast. Severe, sustained stress — the regime where the
    per-unit-leaf graded model provably out-senesces the old step — is reached
    only once the soil is genuinely exhausted (~40 d of drought on a vigorous
    canopy). The scenario is therefore re-shaped to a *short* first drought
    (young canopy grows through it, arming/firing the counter) and a *long*
    second drought on the recovered, still-vigorous canopy, which exhausts the
    soil to Ta/Tp ≈ 0.04 and drives the discriminating collapse. The #420
    discrimination is preserved — just relocated to the cycle that now reaches
    severe stress — and re-verified by temp-reverting to the old
    ``_check_wilt_damage`` step.
    """
    start = date(2024, 6, 1)
    orch = _maize_orch()

    _run(orch, 20, 6.0, start, 0)
    lai_pre1 = orch.canopy.state.lai
    _run(orch, 18, 0.0, start, 20)  # drought 1 (short; arms + fires the counter)
    lai_dr1 = orch.canopy.state.lai
    _run(orch, 20, 8.0, start, 38)  # recovery (resets the lag counter)
    lai_pre2 = orch.canopy.state.lai
    _run(orch, 50, 0.0, start, 58)  # drought 2 (long; exhausts soil -> severe)
    lai_dr2 = orch.canopy.state.lai

    # Cycle 1 arms and fires the stateful counter but the young canopy grows
    # net through the short, mild drought (soil buffer + 5-day lag) — under the
    # corrected PAR basis a short vegetative drought no longer net-removes LAI.
    assert lai_dr1 > lai_pre1, (
        f"young canopy should grow through the short first drought "
        f"({lai_pre1:.2f} -> {lai_dr1:.2f})"
    )
    # The counter must then RESET on recovery so cycle 2 can re-arm.
    assert lai_pre2 > lai_dr1, "canopy should recover between droughts"
    # Discriminating pin (#420, relocated to the severe second drought): an
    # ABSOLUTE removal only the graded per-unit-leaf model meets. The long
    # cycle-2 drought exhausts the soil and the graded model removes ~2.08 LAI
    # (3.25 -> 1.16), while the old size-independent 10%-step removes only ~1.74
    # (3.32 -> 1.59) and FAILS both this pin and the < 1.4 floor below. The 1.9
    # threshold sits between the two behaviours (1.735 < 1.9 < 2.083).
    assert (lai_pre2 - lai_dr2) > 1.9, (
        f"cycle 2 (severe) drought must remove > 1.9 LAI in absolute terms "
        f"({lai_pre2:.2f} -> {lai_dr2:.2f}, removed {lai_pre2 - lai_dr2:.2f}; "
        f"new graded ~2.08, old step ~1.74 fails)"
    )
    # Post-cycle-2 canopy must end materially suppressed (new ~1.16; old ~1.59).
    assert lai_dr2 < 1.4, (
        f"post-cycle-2 canopy must stay below 1.4 LAI "
        f"({lai_dr2:.3f}; new graded ~1.16, old step ~1.59 fails)"
    )
    assert (
        lai_dr2 < lai_pre2
    ), f"cycle 2 drought should reduce LAI again ({lai_pre2:.2f} -> {lai_dr2:.2f})"
