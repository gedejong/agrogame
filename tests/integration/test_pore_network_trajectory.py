"""30-day pore-structure trajectory integration test (#339).

Follow-up to #274/#326: the merged pore-network bundle exposed state and
emitted ``PoreNetworkComputed``, but shipped no test exercising how pore
fractions *evolve over time* under management. This drives the three
soil-structure modules that jointly determine the pore network across a
full 30-day window and asserts the trajectory shape, physical bounds, and
biopore persistence — not merely that a single ``compute()`` runs.

Integration surface (the real coupling points, no orchestrator):
    - ``PoreNetworkModule.compute`` derives per-layer pore fractions from
      texture + aggregation mean-weight-diameter (MWD).
    - ``AggregationModule`` builds macroaggregates biologically (weekly)
      and destroys them on tillage — moving MWD, hence macroporosity.
    - ``BioporeModule`` adds root-channel macropore volume into the pore
      network's ``macro`` pool, decays it daily, and loses plow-zone
      channels to tillage.

Trajectory narrative and its honest mechanism
---------------------------------------------
The #274 acceptance sketch read "tillage -> macro up then decay". In this
engine macroporosity is *aggregate-mediated*: tillage **destroys** soil
structure (Six et al. 2000, SSSAJ — 30-70% of macroaggregates lost in the
plow layer), so tillage drives macroporosity **down**, not up. The plausible
"rise then decay" arc this model produces is therefore biogenic rise
(weekly root/fungal aggregate formation lifts MWD -> macroporosity climbs)
followed by a tillage disturbance that knocks it back below baseline. That
is the scientifically correct sign, and it is what these assertions check.

Biopores, by contrast, *persist*: their decay half-lives are long
(180 d topsoil / 365 d subsoil; Kautz 2015), and tillage only reaches the
plow zone, so subsoil channels survive a pass almost untouched while
topsoil channels lose ~70% but do not vanish.

Refs:
    Six et al. 2000, SSSAJ — tillage destroys 30-70% of macroaggregates.
    Cameron & Buchan 2006, Encyclopedia of Soil Science — air-capacity /
        macroporosity ~0.05-0.15 m3/m3 for medium-textured soil.
    Reynolds et al. 2009, Geoderma — optimal air capacity band.
    Kautz 2015, Soil Tillage Res. — biopore persistence + decay.
    Pierret et al. 2007, Plant Soil 286 — structured-soil biopore density
        50-500 /m2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agrogame.events import EventBus
from agrogame.events.recorder import EventRecorder
from agrogame.soil.aggregation.module import AggregationModule
from agrogame.soil.aggregation.params import SoilAggregationParams
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.biopores.module import BioporeModule
from agrogame.soil.biopores.params import BioporeParams
from agrogame.soil.biopores.state import BioporeState
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network.module import PoreNetworkModule
from agrogame.soil.pore_network.params import PoreNetworkParams
from agrogame.soil.pore_network.state import PoreNetworkState

# --- Scenario constants (literature-anchored) --------------------------

_DAYS = 30
_TILLAGE_DAY = 15  # single moldboard pass mid-window

# Established stand at window start, topsoil > subsoil, inside Pierret
# et al. 2007's structured-soil band [50, 500] /m2.
_START_DENSITY_PER_M2 = (80.0, 60.0, 40.0)

# Cover-crop root turnover, 5 g/m2/day split 50/30/20% by horizon
# (Jackson et al. 1996; Kautz 2015 Table 2). Matches the constant used in
# tests/test_biopores.py so the two suites stay consistent.
_DAILY_DEAD_ROOT_G_M2 = (2.5, 1.5, 1.0)

# Warm, actively growing crop: dense roots + high fungal fraction near the
# aggregation module's temperature optimum, so weekly formation is active.
_ROOT_DENSITY_FRACTIONS = [0.8, 0.5, 0.3]
_FUNGAL_FRACTIONS = [0.5, 0.4, 0.3]
_MEAN_WEEKLY_TEMP_C = 22.0

# Loam air-capacity / macroporosity band (Cameron & Buchan 2006; Reynolds
# et al. 2009). Macroporosity must stay physical across the whole window.
_MACRO_BAND_LO = 0.05
_MACRO_BAND_HI = 0.15


def _loam() -> SoilProfile:
    """3-horizon temperate loam (0-25 / 25-60 / 60-100 cm)."""
    return load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]


@dataclass
class _Trajectory:
    """Per-day series collected while stepping the 30-day window."""

    profile: SoilProfile
    pore_state: PoreNetworkState
    recorder: EventRecorder
    macro_top: list[float] = field(default_factory=list)
    porosity_sum_top: list[float] = field(default_factory=list)
    connectivity_top: list[float] = field(default_factory=list)
    biopore_density_top: list[float] = field(default_factory=list)
    biopore_density_sub: list[float] = field(default_factory=list)


def _run_30_day_trajectory() -> _Trajectory:
    """Drive pore-network + aggregation + biopore modules for 30 days.

    Each day: (weekly) biological aggregate formation -> daily root-channel
    creation -> tillage on ``_TILLAGE_DAY`` -> daily biopore decay ->
    recompute the pore network from the updated aggregation state and
    re-donate the surviving biopore volume into ``macro``.
    """
    bus = EventBus()
    recorder = EventRecorder(bus)

    profile = _loam()
    n = len(profile.layers)
    layer_depths_cm = [layer.depth_cm for layer in profile.layers]

    agg_state = SoilAggregationState.from_layers(n)
    agg_module = AggregationModule(SoilAggregationParams(), agg_state)

    pore_state = PoreNetworkState.empty(n)
    # The pore module is the only one that emits onto the recorded bus;
    # biopore/aggregation events would otherwise drown the signal we assert.
    pore_module = PoreNetworkModule(PoreNetworkParams(), pore_state, event_bus=bus)

    biopore_state = BioporeState.from_layers(n)
    biopore_state.density_per_m2[:] = list(_START_DENSITY_PER_M2)[:n]
    biopore_state.recompute_volume_fraction()
    biopore_module = BioporeModule(BioporeParams(), biopore_state)

    daily_dead = list(_DAILY_DEAD_ROOT_G_M2)[:n]
    traj = _Trajectory(profile=profile, pore_state=pore_state, recorder=recorder)

    for day in range(_DAYS):
        recorder.set_day(day)
        if day % 7 == 0:
            agg_module.weekly_step(
                _ROOT_DENSITY_FRACTIONS, _FUNGAL_FRACTIONS, _MEAN_WEEKLY_TEMP_C
            )
        biopore_module.process_root_turnover(daily_dead)
        if day == _TILLAGE_DAY:
            agg_module.apply_tillage(1.0, layer_depths_cm)
            biopore_module.apply_tillage(1.0, profile)
        biopore_module.apply_decay(profile)

        # End-of-day pore network: recompute from texture + aggregation,
        # then donate the surviving biopore volume into macro.
        pore_module.compute(profile, agg_state)
        biopore_module.reset_pore_network_baseline()
        biopore_module.update_pore_network(pore_state, profile)

        traj.macro_top.append(pore_state.macro[0])
        traj.porosity_sum_top.append(pore_state.total_porosity(0))
        traj.connectivity_top.append(pore_state.connectivity[0])
        traj.biopore_density_top.append(biopore_state.density_per_m2[0])
        traj.biopore_density_sub.append(biopore_state.density_per_m2[-1])

    return traj


# ---------- AC: macroporosity rises (biogenic) then decays (tillage) ----------


def test_macroporosity_rises_then_decays_over_window() -> None:
    """Macroporosity climbs while biology builds structure, then drops at
    the tillage disturbance and stays suppressed for the rest of the window.

    The rise is aggregate-mediated (weekly MWD gain); the decay is the
    tillage pass destroying macroaggregates (Six et al. 2000).
    """
    traj = _run_30_day_trajectory()
    initial = traj.macro_top[0]
    peak_before_tillage = max(traj.macro_top[:_TILLAGE_DAY])
    just_after_tillage = traj.macro_top[_TILLAGE_DAY]
    end = traj.macro_top[-1]

    # Rise: biological aggregate formation lifts macroporosity above the
    # day-0 baseline before the disturbance.
    assert peak_before_tillage > initial + 5e-4, (
        f"Expected biogenic macroporosity rise: peak-before-tillage "
        f"{peak_before_tillage:.5f} vs initial {initial:.5f}"
    )

    # Decay: tillage knocks macroporosity down, and below the day-0
    # baseline (it removes the pre-existing aggregation bonus too).
    assert just_after_tillage < peak_before_tillage - 1e-3, (
        f"Tillage should drop macroporosity from the pre-till peak: "
        f"{just_after_tillage:.5f} vs peak {peak_before_tillage:.5f}"
    )
    assert just_after_tillage < initial, (
        f"Post-tillage macroporosity {just_after_tillage:.5f} should fall "
        f"below the day-0 baseline {initial:.5f}"
    )
    # It stays suppressed through the end of the window (no fast recovery).
    assert end < peak_before_tillage - 1e-3


def test_macroporosity_and_conservation_stay_physical_every_day() -> None:
    """Every day: macroporosity in the loam air-capacity band, pore
    fractions sum to saturation, connectivity in [0, 1]."""
    traj = _run_30_day_trajectory()
    saturation = traj.profile.layers[0].saturation

    assert len(traj.macro_top) == _DAYS
    for day in range(_DAYS):
        macro = traj.macro_top[day]
        assert _MACRO_BAND_LO <= macro <= _MACRO_BAND_HI, (
            f"Day {day}: macroporosity {macro:.4f} outside loam "
            f"air-capacity band [{_MACRO_BAND_LO}, {_MACRO_BAND_HI}]"
        )
        assert abs(traj.porosity_sum_top[day] - saturation) < 1e-6, (
            f"Day {day}: pore fractions sum {traj.porosity_sum_top[day]:.6f} "
            f"!= saturation {saturation:.6f} (conservation violated)"
        )
        assert 0.0 <= traj.connectivity_top[day] <= 1.0


# ---------- AC: biopores persist within Pierret et al. 2007 bounds ----------


def test_biopores_persist_subsoil_survives_tillage() -> None:
    """Subsoil biopores persist across the window and survive a tillage
    pass almost untouched; topsoil (plow-zone) channels lose ~70% but do
    not vanish.

    Ref: Kautz 2015 (long decay half-lives); tillage reaches only the plow
    zone, so channels below ``plow_depth_cm`` are essentially unaffected.
    """
    traj = _run_30_day_trajectory()

    top_pre = traj.biopore_density_top[_TILLAGE_DAY - 1]
    top_post = traj.biopore_density_top[_TILLAGE_DAY]
    sub_pre = traj.biopore_density_sub[_TILLAGE_DAY - 1]
    sub_post = traj.biopore_density_sub[_TILLAGE_DAY]

    # Topsoil: tillage destroys a large share of plow-zone channels.
    assert top_post < 0.5 * top_pre, (
        f"Tillage should destroy most topsoil biopores: "
        f"{top_post:.1f} vs pre-till {top_pre:.1f} /m2"
    )
    assert top_post > 0.0, "Some topsoil channels should survive one pass"

    # Subsoil (below plow depth): essentially untouched by the pass.
    assert abs(sub_post - sub_pre) < 0.02 * sub_pre, (
        f"Subsoil biopores should survive tillage nearly intact: "
        f"{sub_post:.2f} vs {sub_pre:.2f} /m2"
    )

    # Persistence contrast: subsoil retains far more of its channels
    # through the disturbance than the plow-zone topsoil does.
    assert (sub_post / sub_pre) > (top_post / top_pre)

    # Whole-window persistence: subsoil density at day 30 is still within
    # ~10% of where it started (slow decay only).
    assert traj.biopore_density_sub[-1] >= 0.9 * traj.biopore_density_sub[0], (
        f"Subsoil biopores should persist over 30 days: "
        f"{traj.biopore_density_sub[-1]:.1f} vs start "
        f"{traj.biopore_density_sub[0]:.1f} /m2"
    )


def test_biopore_density_within_pierret_bounds_all_days() -> None:
    """Biopore density stays within Pierret et al. 2007's physical
    envelope (0, 500] /m2 for every layer on every day."""
    traj = _run_30_day_trajectory()
    for day in range(_DAYS):
        for density in (
            traj.biopore_density_top[day],
            traj.biopore_density_sub[day],
        ):
            assert 0.0 < density <= 500.0, (
                f"Day {day}: biopore density {density:.1f} /m2 outside "
                f"Pierret 2007 envelope (0, 500]"
            )


# ---------- AC: pore-structure event captured across the whole window ----------


def test_pore_event_recorded_every_day_of_window() -> None:
    """The ``PoreNetworkComputed`` diagnostic is captured by
    ``EventRecorder`` on every day of the trajectory (one per layer),
    tagged with the correct day index — the time-series the visualization
    tooling consumes."""
    traj = _run_30_day_trajectory()
    n_layers = len(traj.profile.layers)

    pore_events = [
        e for e in traj.recorder.events if e.event_type == "PoreNetworkComputed"
    ]
    # One event per layer per day for the full window.
    assert len(pore_events) == _DAYS * n_layers

    days_seen = {e.day_index for e in pore_events}
    assert days_seen == set(range(_DAYS)), "Every day should be tagged"

    # Spot-check the last day's payloads. The event is emitted inside
    # ``compute()`` (before biopore donation augments ``macro``), so its
    # fractions are the texture+aggregation snapshot: assert that snapshot's
    # own invariants rather than equality to the post-donation state.
    last_day_events = sorted(
        (e for e in pore_events if e.day_index == _DAYS - 1),
        key=lambda e: e.data["layer"],
    )
    assert len(last_day_events) == n_layers
    for i, rec in enumerate(last_day_events):
        for field_name in ("layer", "macro", "meso", "micro", "crypto", "connectivity"):
            assert field_name in rec.data
        assert rec.data["layer"] == i
        assert 0.0 <= rec.data["connectivity"] <= 1.0
        recorded_sum = (
            rec.data["macro"]
            + rec.data["meso"]
            + rec.data["micro"]
            + rec.data["crypto"]
        )
        expected_sat = traj.profile.layers[i].saturation
        assert abs(recorded_sum - expected_sat) < 1e-9, (
            f"Layer {i}: recorded pore fractions sum {recorded_sum:.6f} "
            f"!= saturation {expected_sat:.6f}"
        )
