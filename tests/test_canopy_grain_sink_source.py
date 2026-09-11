"""Unit tests for the sink-source grain model (#321).

Covers grain-number setting during the peri-anthesis window (including the
grain-set floor), freezing + diagnostic event, kernel-weight fill kinetics,
heat/reserve effects, the hi_max cap on both grain paths, harvest reset,
state persistence, and the soybean preset's sink-source migration. The
legacy fixed-HI allocation itself is exercised in ``test_canopy_events.py``.
"""

from __future__ import annotations

from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.presets import _load_crop_presets_cached, load_crop_presets
from agrogame.soil.phenology import StageChanged, PhenologyStage
from agrogame.soil.phenology.events import GddAccumulated
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.soil.canopy.events import Harvested, GrainNumberSet
from agrogame.soil.canopy.types import CanopyState


def _sink_params(**overrides: float) -> CanopyParams:
    base: dict[str, float] = {
        "extinction_coefficient_k": 0.6,
        "radiation_use_efficiency_g_per_mj": 3.0,
        "specific_leaf_area_m2_per_g": 0.02,
        "lai_max": 6.0,
        "senescence_rate_per_day": 0.0,
        "leaf_fraction_grain_fill": 0.1,
        "grains_per_g_source": 50.0,
        "grain_set_window_gdd": 100.0,
        "potential_kernel_weight_mg": 40.0,
        "kernel_fill_rate_mg_per_grain_day": 2.0,
        "hi_max": 0.55,
    }
    base.update(overrides)
    return CanopyParams(**base)  # type: ignore[arg-type]


def _enter_grain_fill(
    canopy: CanopyModule, bus: EventBus, at_gdd: float = 900.0
) -> None:
    bus.emit(
        StageChanged(
            from_stage=PhenologyStage.FLOWERING,
            to_stage=PhenologyStage.GRAIN_FILL,
            at_gdd=at_gdd,
        )
    )


def _step(canopy: CanopyModule, bus: EventBus, total_gdd: float) -> None:
    bus.emit(GddAccumulated(daily_gdd=1.0, total_gdd=total_gdd))
    canopy.daily_step(
        incident_shortwave_mj_m2=10.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )


def test_grain_number_accumulates_in_window_then_freezes_with_event() -> None:
    bus = EventBus()
    events: list[GrainNumberSet] = []
    bus.subscribe(GrainNumberSet, lambda e: events.append(e))
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    assert canopy._lag_start_biomass == 500.0
    assert canopy.state.grain_number == 0.0

    _step(canopy, bus, total_gdd=950.0)  # in window
    gn1 = canopy.state.grain_number
    assert gn1 > 0.0

    _step(canopy, bus, total_gdd=990.0)  # still in window
    gn2 = canopy.state.grain_number
    assert gn2 > gn1
    assert events == []  # not frozen yet

    _step(canopy, bus, total_gdd=1010.0)  # past window_end (900+100)
    assert canopy.state.grain_number == gn2  # frozen
    assert len(events) == 1
    assert events[0].grain_number == gn2
    assert events[0].at_gdd == 1010.0


def test_kernel_weight_bounded_by_potential() -> None:
    """Cumulative grain cannot exceed number x potential kernel weight."""
    bus = EventBus()
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 5.0
    canopy.state.biomass_g_m2 = 400.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    # Fill well past the window for many days.
    for i in range(60):
        _step(canopy, bus, total_gdd=950.0 + i * 20.0)
    gn = canopy.state.grain_number
    assert gn > 0.0
    kernel_weight_mg = canopy.state.grain_biomass_g_m2 / gn * 1000.0
    # Never exceeds potential (40 mg); reaches it when source is ample.
    assert kernel_weight_mg <= 40.0 + 1e-6


def test_heat_reduces_grain_fill() -> None:
    """heat_grain_factor < 1 during fill lowers accumulated grain."""

    def run(heat_factor: float) -> float:
        bus = EventBus()
        canopy = CanopyModule(_sink_params(), event_bus=bus)
        canopy.state.lai = 5.0
        canopy.state.biomass_g_m2 = 400.0
        _enter_grain_fill(canopy, bus, at_gdd=900.0)
        # Set grain number in an unstressed window first.
        for i in range(3):
            _step(canopy, bus, total_gdd=950.0 + i * 20.0)
        # Then fill with a heat factor for a few days.
        for i in range(10):
            bus.emit(GddAccumulated(daily_gdd=1.0, total_gdd=1050.0 + i * 20.0))
            canopy.daily_step(
                incident_shortwave_mj_m2=10.0,
                temp_factor=1.0,
                water_stress=1.0,
                n_stress=1.0,
                heat_grain_factor=heat_factor,
            )
        return canopy.state.grain_biomass_g_m2

    assert run(0.4) < run(1.0)


def test_reserves_fill_grain_when_source_is_low() -> None:
    """Stem + leaf reserves are remobilised to meet grain demand."""
    bus = EventBus()
    canopy = CanopyModule(
        _sink_params(remobilization_fraction=0.2, leaf_remob_fraction=0.1),
        event_bus=bus,
    )
    canopy.state.lai = 0.05  # negligible light interception -> tiny source
    canopy.state.biomass_g_m2 = 600.0
    canopy.state.stem_biomass_g_m2 = 300.0  # ample reserves
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    # Grain number is set from lag growth; seed it directly so demand > source.
    canopy.state.grain_number = 8000.0
    grain_before = canopy.state.grain_biomass_g_m2
    stem_before = canopy.state.stem_biomass_g_m2
    _step(canopy, bus, total_gdd=1010.0)
    assert canopy.state.grain_biomass_g_m2 > grain_before  # grain grew
    assert canopy.state.stem_biomass_g_m2 < stem_before  # from reserves


def test_hi_max_cap_bounds_grain() -> None:
    """Grain never exceeds hi_max x total biomass; surplus returns to stem."""
    bus = EventBus()
    canopy = CanopyModule(
        _sink_params(hi_max=0.2, remobilization_fraction=0.5, leaf_remob_fraction=0.3),
        event_bus=bus,
    )
    canopy.state.lai = 5.0
    canopy.state.biomass_g_m2 = 1000.0
    canopy.state.stem_biomass_g_m2 = 800.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    canopy.state.grain_number = 50000.0  # huge sink to force the cap
    for i in range(5):
        _step(canopy, bus, total_gdd=1010.0 + i * 20.0)
        assert canopy.state.grain_biomass_g_m2 <= 0.2 * canopy.state.biomass_g_m2 + 1e-6


def test_harvest_resets_grain_number_and_window() -> None:
    bus = EventBus()
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    _step(canopy, bus, total_gdd=950.0)  # in window: set grain number
    _step(canopy, bus, total_gdd=1010.0)  # freeze
    assert canopy.state.grain_number > 0.0
    bus.emit(Harvested(fraction_remaining=0.0))
    assert canopy.state.grain_number == 0.0
    assert canopy._grain_number_frozen is False
    assert canopy._lag_start_biomass == 0.0


def test_grain_number_recomputes_across_two_cycles() -> None:
    """After harvest, a second grain-fill cycle sets a fresh grain number.

    Guards against stale grain-number/window state leaking between seasons.
    """
    bus = EventBus()
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0

    # Cycle 1
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    _step(canopy, bus, total_gdd=950.0)
    _step(canopy, bus, total_gdd=1010.0)
    gn_cycle1 = canopy.state.grain_number
    assert gn_cycle1 > 0.0

    # Harvest resets pools and window state.
    bus.emit(Harvested(fraction_remaining=0.1))
    assert canopy.state.grain_number == gn_cycle1 * 0.1

    # Cycle 2: regrow, re-enter grain fill; grain number is set afresh.
    canopy.state.biomass_g_m2 = 600.0
    _enter_grain_fill(canopy, bus, at_gdd=2000.0)
    assert canopy.state.grain_number == 0.0  # reset on re-entry
    assert canopy._lag_start_biomass == 600.0
    _step(canopy, bus, total_gdd=2050.0)
    assert canopy.state.grain_number > 0.0


def test_legacy_high_hi_clamps_stem_nonnegative() -> None:
    """Legacy path: HI > (1 - leaf_fraction) must not drive stem negative."""
    bus = EventBus()
    # grains_per_g_source=0 -> legacy fixed-HI; HI 0.95 > (1 - 0.15)=0.85.
    params = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.0,
        leaf_fraction_grain_fill=0.15,
        harvest_index=0.95,
    )
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = 3.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    _step(canopy, bus, total_gdd=950.0)
    assert canopy.state.stem_biomass_g_m2 >= 0.0
    assert canopy.state.grain_biomass_g_m2 > 0.0


def test_canopy_state_grain_number_round_trips() -> None:
    state = CanopyState(
        lai=3.0,
        biomass_g_m2=800.0,
        stem_biomass_g_m2=200.0,
        grain_biomass_g_m2=300.0,
        grain_number=15000.0,
    )
    restored = CanopyState.from_dict(state.to_dict())
    assert restored.grain_number == 15000.0
    assert restored.grain_biomass_g_m2 == 300.0
    # Backward compat: missing grain_number defaults to 0.0.
    legacy = CanopyState.from_dict({"lai": 1.0, "biomass_g_m2": 10.0})
    assert legacy.grain_number == 0.0


def test_legacy_fixed_hi_path_capped_at_hi_max() -> None:
    """Legacy path: compounding stem remobilisation stops at hi_max x biomass."""
    bus = EventBus()
    params = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.0,
        leaf_fraction_grain_fill=0.1,
        harvest_index=0.5,
        remobilization_fraction=0.5,
        hi_max=0.3,
    )
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0
    canopy.state.stem_biomass_g_m2 = 300.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    for i in range(30):
        _step(canopy, bus, total_gdd=950.0 + i * 20.0)
        hi = canopy.state.grain_biomass_g_m2 / canopy.state.biomass_g_m2
        assert hi <= 0.3 + 1e-9
    # 50 %/d remobilisation of a 300 g stem would push HI far past 0.3, so
    # the cap binds; the surplus goes back to stem and the pools stay
    # within the shoot total.
    assert canopy.state.grain_biomass_g_m2 > 0.0
    assert abs(canopy.state.grain_biomass_g_m2 - 0.3 * canopy.state.biomass_g_m2) < 1e-9
    assert canopy.state.stem_biomass_g_m2 >= 0.0
    assert (
        canopy.state.stem_biomass_g_m2 + canopy.state.grain_biomass_g_m2
        <= canopy.state.biomass_g_m2 + 1e-9
    )


def test_grain_set_floor_when_window_has_no_growth() -> None:
    """A window without assimilate still sets grains from window-start biomass."""
    bus = EventBus()
    events: list[GrainNumberSet] = []
    bus.subscribe(GrainNumberSet, lambda e: events.append(e))
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0
    canopy.state.stem_biomass_g_m2 = 300.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    for gdd in (920.0, 960.0, 1000.0):  # dark days spanning the whole window
        bus.emit(GddAccumulated(daily_gdd=1.0, total_gdd=gdd))
        canopy.daily_step(
            incident_shortwave_mj_m2=0.0,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
    expected_floor = 50.0 * 0.02 * 500.0  # grains/g x floor frac x start biomass
    assert canopy.state.biomass_g_m2 == 500.0
    assert abs(canopy.state.grain_number - expected_floor) < 1e-9
    assert canopy.state.grain_number > 0.0

    _step(canopy, bus, total_gdd=1010.0)  # window closed: frozen at the floor
    assert abs(canopy.state.grain_number - expected_floor) < 1e-9
    assert len(events) == 1
    assert abs(events[0].grain_number - expected_floor) < 1e-9

    for i in range(20):  # filling the small population gives a positive HI
        _step(canopy, bus, total_gdd=1030.0 + i * 20.0)
    assert canopy.state.grain_biomass_g_m2 > 0.0
    assert canopy.state.grain_biomass_g_m2 / canopy.state.biomass_g_m2 > 0.0


def test_grain_set_floor_inactive_when_window_growth_exceeds_it() -> None:
    """With ample window growth grain number stays assimilate-driven."""
    bus = EventBus()
    canopy = CanopyModule(_sink_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 500.0
    _enter_grain_fill(canopy, bus, at_gdd=900.0)
    for gdd in (920.0, 960.0, 1000.0):
        _step(canopy, bus, total_gdd=gdd)
    window_growth = canopy.state.biomass_g_m2 - 500.0
    assert 50.0 * window_growth > 50.0 * 0.02 * 500.0
    assert abs(canopy.state.grain_number - 50.0 * window_growth) < 1e-9


def test_soybean_preset_on_sink_source_path_with_hi_ceiling() -> None:
    """Soybean sets seed number from window assimilate and caps HI at 0.45."""
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    params = lib.get_preset("soybean").canopy
    assert params.grains_per_g_source == 8.0
    assert params.grain_set_window_gdd == 250.0
    assert params.potential_kernel_weight_mg == 160.0
    assert params.kernel_fill_rate_mg_per_grain_day == 5.0
    assert params.hi_max == 0.45
    assert params.harvest_index == 0.40  # legacy fallback value kept

    bus = EventBus()
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = 3.5
    canopy.state.biomass_g_m2 = 325.0
    canopy.state.stem_biomass_g_m2 = 180.0
    _enter_grain_fill(canopy, bus, at_gdd=700.0)
    # Flowering (700 GDD) to maturity (1400 GDD) at ~9 GDD/day, the pace of
    # a highland tropical season.
    for day in range(1, 79):
        _step(canopy, bus, total_gdd=700.0 + 9.0 * day)
    assert canopy.state.grain_number > 0.0
    hi = canopy.state.grain_biomass_g_m2 / canopy.state.biomass_g_m2
    # Seed number x potential seed weight, not the cap, bounds the yield.
    assert 0.25 <= hi < 0.45
    seed_weight_mg = canopy.state.grain_biomass_g_m2 / canopy.state.grain_number * 1e3
    assert seed_weight_mg <= 160.0 + 1e-6
    assert (
        canopy.state.stem_biomass_g_m2 + canopy.state.grain_biomass_g_m2
        <= canopy.state.biomass_g_m2 + 1e-9
    )
