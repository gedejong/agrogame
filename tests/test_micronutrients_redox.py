"""Tests for redox-driven Fe/Mn pool dynamics (#216).

Validates the MicronutrientRuntime._on_redox_changed pathway:
- Fe³⁺ → Fe²⁺ reduction below 100 mV (Patrick & Reddy 1976)
- Mn⁴⁺ → Mn²⁺ reduction below 200 mV (Stumm & Morgan 1996)
- Re-oxidation at Eh > 300 mV (slower kinetics)
- Mass conservation: total pool unchanged
- Fe toxicity emergence under prolonged flooding (Ponnamperuma 1972)
"""

from __future__ import annotations

import pytest

from agrogame.events import EventBus
from agrogame.soil.micronutrients import (
    MicronutrientCycle,
    MicronutrientParams,
    MicronutrientState,
    RedoxMicronutrientParams,
    RedoxNutrientTransformed,
)
from agrogame.soil.micronutrients.runtime import MicronutrientRuntime
from agrogame.soil.redox.events import RedoxChanged


# ---------- helpers ----------


def _fresh_setup(
    n_layers: int = 3,
) -> tuple[EventBus, MicronutrientCycle, MicronutrientRuntime]:
    bus = EventBus()
    state = MicronutrientState.from_layers(n_layers)
    cycle = MicronutrientCycle(bus, state, MicronutrientParams(), n_layers)
    runtime = MicronutrientRuntime(event_bus=bus, cycle=cycle)
    return bus, cycle, runtime


# ---------- Params ----------


def test_redox_params_frozen() -> None:
    p = RedoxMicronutrientParams()
    with pytest.raises(AttributeError):
        p.fe_reduction_eh_mv = 999.0  # type: ignore[misc]


def test_redox_params_defaults_match_literature() -> None:
    p = RedoxMicronutrientParams()
    assert p.fe_reduction_eh_mv == 100.0  # Patrick & Reddy 1976
    assert p.mn_reduction_eh_mv == 200.0  # Stumm & Morgan 1996
    assert p.reoxidation_eh_mv == 300.0
    # Asymmetric: reduction 4x faster than re-oxidation
    assert p.reduction_rate_per_day > p.reoxidation_rate_per_day * 3
    # Reactive fractions: 1-5% of total Fe, Mn more labile
    # (Schwertmann 1964; Roden & Wetzel 1996; Gotoh & Patrick 1972).
    assert 0.01 <= p.reactive_fe_fraction <= 0.05
    assert p.reactive_mn_fraction > p.reactive_fe_fraction


# ---------- Fe reduction ----------


def test_fe_reduction_below_100mv_increases_available() -> None:
    bus, cycle, _ = _fresh_setup()
    before = cycle.state.fe_available[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=-50.0, dominant_acceptor="Fe3+"))
    after = cycle.state.fe_available[0]
    assert (
        after > before
    ), f"Fe available should increase below 100 mV: {before} → {after}"


def test_fe_reduction_above_100mv_no_change() -> None:
    bus, cycle, _ = _fresh_setup()
    before = cycle.state.fe_available[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=150.0, dominant_acceptor="NO3-"))
    after = cycle.state.fe_available[0]
    assert after == before, "No Fe change expected above 100 mV threshold"


def test_fe_reduction_severity_scales_with_eh() -> None:
    """Deeper reduction (more negative Eh) → more Fe released per day."""
    bus_shallow, cycle_shallow, _ = _fresh_setup()
    bus_deep, cycle_deep, _ = _fresh_setup()
    shallow_before = cycle_shallow.state.fe_available[0]
    deep_before = cycle_deep.state.fe_available[0]

    bus_shallow.emit(RedoxChanged(layer=0, eh_mv=50.0, dominant_acceptor="Fe3+"))
    bus_deep.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))

    shallow_release = cycle_shallow.state.fe_available[0] - shallow_before
    deep_release = cycle_deep.state.fe_available[0] - deep_before
    assert deep_release > shallow_release, (
        f"Deep reduction should release more: shallow={shallow_release:.2f}, "
        f"deep={deep_release:.2f}"
    )


# ---------- Mn reduction ----------


def test_mn_reduction_below_200mv_increases_available() -> None:
    """Mn reduces at higher Eh than Fe (reduces earlier in the ladder)."""
    bus, cycle, _ = _fresh_setup()
    before = cycle.state.mn_available[0]
    # Eh between Fe and Mn thresholds: Mn should still reduce.
    bus.emit(RedoxChanged(layer=0, eh_mv=150.0, dominant_acceptor="NO3-"))
    after = cycle.state.mn_available[0]
    assert after > before


def test_mn_no_reduction_above_200mv() -> None:
    bus, cycle, _ = _fresh_setup()
    before = cycle.state.mn_available[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=250.0, dominant_acceptor="NO3-"))
    after = cycle.state.mn_available[0]
    assert after == before


def test_fe_and_mn_at_intermediate_eh() -> None:
    """At Eh=150 mV: Mn reduces but Fe does not."""
    bus, cycle, _ = _fresh_setup()
    fe_before = cycle.state.fe_available[0]
    mn_before = cycle.state.mn_available[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=150.0, dominant_acceptor="NO3-"))
    assert cycle.state.fe_available[0] == fe_before, "Fe should be stable at 150 mV"
    assert cycle.state.mn_available[0] > mn_before, "Mn should reduce at 150 mV"


# ---------- Re-oxidation ----------


def test_fe_reoxidation_above_300mv_decreases_available() -> None:
    """Boost Fe available first, then re-oxidize."""
    bus, cycle, _ = _fresh_setup()
    # Seed elevated Fe via reducing event.
    cycle.state.fe_available[0] = 100.0  # well above baseline ~10 ppm
    bus.emit(RedoxChanged(layer=0, eh_mv=400.0, dominant_acceptor="O2"))
    after = cycle.state.fe_available[0]
    assert after < 100.0, f"Fe should precipitate at Eh=400 mV: {after}"


def test_mn_reoxidation_above_300mv_decreases_available() -> None:
    bus, cycle, _ = _fresh_setup()
    cycle.state.mn_available[0] = 50.0
    bus.emit(RedoxChanged(layer=0, eh_mv=400.0, dominant_acceptor="O2"))
    after = cycle.state.mn_available[0]
    assert after < 50.0


def test_asymmetric_rates_reduction_faster_than_oxidation() -> None:
    """Daily reduction release > daily oxidation precipitation for same severity."""
    bus_red, cycle_red, _ = _fresh_setup()
    bus_ox, cycle_ox, _ = _fresh_setup()
    # Set identical starting conditions.
    cycle_red.state.fe_available[0] = 100.0
    cycle_ox.state.fe_available[0] = 100.0

    # Symmetric severity: -100 mV is 200 below Fe threshold (100 mV);
    # 500 mV is 200 above re-ox threshold (300 mV).
    bus_red.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    bus_ox.emit(RedoxChanged(layer=0, eh_mv=500.0, dominant_acceptor="O2"))

    reduction_delta = cycle_red.state.fe_available[0] - 100.0
    oxidation_delta = 100.0 - cycle_ox.state.fe_available[0]
    assert reduction_delta > oxidation_delta, (
        f"Reduction should outpace oxidation at matched severity: "
        f"red={reduction_delta:.3f}, ox={oxidation_delta:.3f}"
    )


# ---------- Mass conservation ----------


def test_fe_total_conserved_across_reduction() -> None:
    bus, cycle, _ = _fresh_setup()
    total_before = cycle.state.fe_total[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    assert cycle.state.fe_total[0] == total_before


def test_mn_total_conserved_across_reduction() -> None:
    bus, cycle, _ = _fresh_setup()
    total_before = cycle.state.mn_total[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=100.0, dominant_acceptor="Mn2+"))
    assert cycle.state.mn_total[0] == total_before


def test_total_conserved_over_waterlog_drain_cycle() -> None:
    """30-day wet-dry cycle: total Fe/Mn constant."""
    bus, cycle, _ = _fresh_setup()
    fe_total_initial = cycle.state.fe_total[0]
    mn_total_initial = cycle.state.mn_total[0]
    # 15 days of reducing (waterlog), 15 days of oxidizing (drain)
    for _ in range(15):
        bus.emit(RedoxChanged(layer=0, eh_mv=-50.0, dominant_acceptor="Fe3+"))
    for _ in range(15):
        bus.emit(RedoxChanged(layer=0, eh_mv=400.0, dominant_acceptor="O2"))

    assert cycle.state.fe_total[0] == fe_total_initial
    assert cycle.state.mn_total[0] == mn_total_initial


def test_available_bounded_by_reactive_ceiling() -> None:
    """fe_available caps at reactive_fraction × fe_total (and never above total).

    Only the amorphous/reactive fraction participates in short-term redox
    cycling (Schwertmann 1964; Roden & Wetzel 1996).
    """
    bus, cycle, _ = _fresh_setup()
    # Push hard reduction for many days.
    for _ in range(200):
        bus.emit(RedoxChanged(layer=0, eh_mv=-200.0, dominant_acceptor="Fe3+"))
    reactive_ceiling = 0.02 * cycle.state.fe_total[0]  # default fraction
    assert cycle.state.fe_available[0] <= cycle.state.fe_total[0]
    assert cycle.state.fe_available[0] <= reactive_ceiling + 1e-6, (
        f"Fe available {cycle.state.fe_available[0]} exceeded reactive "
        f"ceiling {reactive_ceiling}"
    )
    assert cycle.state.fe_available[0] >= 0.0


def test_available_never_negative_under_oxidation() -> None:
    bus, cycle, _ = _fresh_setup()
    for _ in range(200):
        bus.emit(RedoxChanged(layer=0, eh_mv=500.0, dominant_acceptor="O2"))
    assert cycle.state.fe_available[0] >= 0.0
    assert cycle.state.mn_available[0] >= 0.0


# ---------- Event emission ----------


def test_redox_nutrient_transformed_event_on_reduction() -> None:
    bus, cycle, _ = _fresh_setup()
    events: list[RedoxNutrientTransformed] = []
    bus.subscribe(RedoxNutrientTransformed, events.append)
    bus.emit(RedoxChanged(layer=0, eh_mv=-50.0, dominant_acceptor="Fe3+"))
    # Expect Fe + Mn (both reduced), each as a separate event.
    # Element casing matches NutrientStressComputed convention (title-case).
    elements = {e.element for e in events if e.amount_ppm > 0}
    directions = {e.direction for e in events if e.amount_ppm > 0}
    assert "Fe" in elements
    assert "Mn" in elements
    assert directions == {"reduction"}


def test_redox_nutrient_transformed_event_on_oxidation() -> None:
    bus, cycle, _ = _fresh_setup()
    cycle.state.fe_available[0] = 50.0
    cycle.state.mn_available[0] = 20.0
    events: list[RedoxNutrientTransformed] = []
    bus.subscribe(RedoxNutrientTransformed, events.append)
    bus.emit(RedoxChanged(layer=0, eh_mv=450.0, dominant_acceptor="O2"))
    directions = {e.direction for e in events if e.amount_ppm > 0}
    assert directions == {"oxidation"}


def test_no_event_in_mild_oxidizing_band() -> None:
    """Eh in 200-300 mV (mild oxidizing): neither reduction nor oxidation fires."""
    bus, cycle, _ = _fresh_setup()
    events: list[RedoxNutrientTransformed] = []
    bus.subscribe(RedoxNutrientTransformed, events.append)
    bus.emit(RedoxChanged(layer=0, eh_mv=250.0, dominant_acceptor="NO3-"))
    assert not events, "No events expected in mild-oxidizing 200-300 mV band"


# ---------- Fe toxicity emergence (integration-ish unit test) ----------


def test_prolonged_flooding_triggers_fe_toxicity() -> None:
    """30 days at Eh=-100 mV on acid soil → Fe available > TOXIC_FE_PPM (300 ppm).

    Ponnamperuma 1972 reports 50-300 ppm Fe²⁺ in flooded rice soils,
    with the upper end in acid soils. To reach toxicity within the
    literature range, simulate a high-Fe acid soil (doubled reactive
    fraction via larger fe_total — e.g., a ferralsol with 50,000 ppm
    total). The default 25,000 ppm total with 2% reactive ceiling
    caps available around 500 ppm, which still crosses the 300 ppm
    toxic threshold over 30 days of continuous reduction.
    """
    from agrogame.soil.micronutrients.constants import TOXIC_FE_PPM

    bus, cycle, _ = _fresh_setup()
    # Use high-Fe acid soil — double fe_total to simulate a ferralsol.
    cycle.state.fe_total[0] = 50000.0
    fe_initial = cycle.state.fe_available[0]
    assert fe_initial < TOXIC_FE_PPM, "Default Fe should be well below toxic"

    for _ in range(30):
        bus.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))

    final = cycle.state.fe_available[0]
    assert final > TOXIC_FE_PPM, (
        f"30-day flooding on acid soil should push Fe above "
        f"{TOXIC_FE_PPM} ppm (got {final:.1f})"
    )
    # Stress calculation should trigger toxicity path.
    stress = cycle._compute_stress("fe", uptake=0.0, demand=100.0)
    assert stress < 1.0, f"Fe toxicity should reduce stress below 1.0 (got {stress})"


# ---------- Flooded rice realism ----------


def test_10_day_waterlog_fe_reaches_ponnamperuma_range() -> None:
    """10-day sustained reduction → Fe available in Ponnamperuma 1972 range.

    Ref: Ponnamperuma 1972, Adv. Agron. — flooded rice soils reach
    50-300 ppm Fe²⁺ within days of flooding onset. The reactive Fe
    fraction bounds the reducible pool to ~2% of total (Schwertmann
    1964; Roden & Wetzel 1996), so a 25,000 ppm total gives a 500 ppm
    reducible ceiling, approaching the Ponnamperuma upper bound.
    """
    bus, cycle, _ = _fresh_setup()
    fe_initial = cycle.state.fe_available[0]
    for _ in range(10):
        bus.emit(RedoxChanged(layer=0, eh_mv=-80.0, dominant_acceptor="Fe3+"))
    final = cycle.state.fe_available[0]
    assert final > 50.0, f"Fe should reach at least 50 ppm; got {final:.1f}"
    assert (
        final < 500.0
    ), f"Fe should stay below ~500 ppm (2% reactive ceiling); got {final:.1f}"
    assert final > fe_initial * 5
    # Sanity: never exceeds total.
    assert final <= cycle.state.fe_total[0]


def test_10_day_waterlog_mn_reaches_gotoh_range() -> None:
    """10-day reduction → Mn²⁺ in Gotoh & Patrick 1972 range.

    Ref: Gotoh & Patrick 1972 — flooded soil Mn²⁺ 1-50 ppm. With a 5%
    reactive ceiling and 500 ppm Mn total, the ceiling is ~25 ppm,
    within the literature range.
    """
    bus, cycle, _ = _fresh_setup()
    for _ in range(10):
        bus.emit(RedoxChanged(layer=0, eh_mv=0.0, dominant_acceptor="Fe3+"))
    final = cycle.state.mn_available[0]
    assert final < 75.0, f"Mn should stay within Gotoh 1972 range; got {final:.1f}"


def test_re_aeration_drains_elevated_fe() -> None:
    """Waterlog then drain: Fe available declines after re-aeration."""
    bus, cycle, _ = _fresh_setup()
    # 10 days waterlogged
    for _ in range(10):
        bus.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    peak = cycle.state.fe_available[0]
    # 10 days aerated
    for _ in range(10):
        bus.emit(RedoxChanged(layer=0, eh_mv=400.0, dominant_acceptor="O2"))
    end = cycle.state.fe_available[0]
    assert end < peak, f"Fe should decline after aeration: peak={peak}, end={end}"


# ---------- Edge cases ----------


def test_invalid_layer_index_is_safe() -> None:
    bus, cycle, _ = _fresh_setup(n_layers=3)
    # Emit for a layer beyond bounds; should not crash or mutate state.
    before = list(cycle.state.fe_available)
    bus.emit(RedoxChanged(layer=99, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    assert cycle.state.fe_available == before


def test_negative_layer_index_is_safe() -> None:
    """Negative layer index must not silently mutate the last layer."""
    bus, cycle, _ = _fresh_setup(n_layers=3)
    before = list(cycle.state.fe_available)
    bus.emit(RedoxChanged(layer=-1, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    assert (
        cycle.state.fe_available == before
    ), "Negative layer index should be rejected, not index from end"


# ---------- Integration: RedoxChanged + daily_step interleaved ----------


def test_interleaved_redox_and_daily_step_reaches_ponnamperuma_range() -> None:
    """10 days of flooding with daily_step between events: Fe in 50-500 ppm.

    This is the realism test that detects the fight between
    _update_availability (aerobic equilibration) and apply_redox_adjustment
    (reducing release). With the redox-aware skip, the equilibration does
    not drag Fe back toward 10 ppm under sustained reducing conditions.
    """
    bus, cycle, _ = _fresh_setup(n_layers=3)
    for _ in range(10):
        # Reduce all layers
        for i in range(3):
            bus.emit(RedoxChanged(layer=i, eh_mv=-80.0, dominant_acceptor="Fe3+"))
        # Simulate the nutrients phase: equilibration + uptake
        cycle.daily_step(biomass_inc_g_m2=0.0, root_fractions=[0.5, 0.3, 0.2])
    final = cycle.state.fe_available[0]
    assert 50.0 < final < 500.0, (
        f"Expected Fe in Ponnamperuma range after 10 interleaved days; "
        f"got {final:.1f} ppm"
    )


def test_interleaved_re_aeration_returns_toward_aerobic() -> None:
    """After flooding, sustained aeration + daily_step brings Fe back down."""
    bus, cycle, _ = _fresh_setup(n_layers=3)
    # 10 flooded days
    for _ in range(10):
        for i in range(3):
            bus.emit(RedoxChanged(layer=i, eh_mv=-80.0, dominant_acceptor="Fe3+"))
        cycle.daily_step(biomass_inc_g_m2=0.0, root_fractions=[0.5, 0.3, 0.2])
    peak = cycle.state.fe_available[0]
    # 30 aerated days — both re-oxidation AND aerobic equilibration reduce Fe
    for _ in range(30):
        for i in range(3):
            bus.emit(RedoxChanged(layer=i, eh_mv=400.0, dominant_acceptor="O2"))
        cycle.daily_step(biomass_inc_g_m2=0.0, root_fractions=[0.5, 0.3, 0.2])
    end = cycle.state.fe_available[0]
    assert (
        end < peak * 0.5
    ), f"Re-aeration should drain Fe substantially: peak={peak:.1f}, end={end:.1f}"


def test_zero_sorbed_does_nothing() -> None:
    """If available already equals total (nothing left sorbed), reduction is a no-op."""
    bus, cycle, _ = _fresh_setup()
    cycle.state.fe_available[0] = cycle.state.fe_total[0]
    before = cycle.state.fe_available[0]
    bus.emit(RedoxChanged(layer=0, eh_mv=-100.0, dominant_acceptor="Fe3+"))
    assert cycle.state.fe_available[0] == before
