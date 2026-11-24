"""pH enters nitrification once, through the DSSAT-CSM nitrifier factor (#558).

Before #558 nitrification multiplied an uncited pH triangle by a microbial
activity index that already carried the heterotroph (Rousk et al. 2009) pH
response. It now applies one factor, ``min(1, 0.33 pH - 1.36)`` floored at 0
(DSSAT-CSM v4.8 ``SOILNI.for``), to the activity index without its pH term.
Mineralisation keeps the pH-inclusive index.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.microbes.events import MicrobialActivityComputed
from agrogame.soil.models import SoilProfile
from agrogame.soil.microbes.responses import EnvironmentalResponses
from agrogame.soil.nitrogen import NitrogenCycle, SoilNitrogenState
from agrogame.soil.nitrogen.events import NitrificationOccurred
from agrogame.soil.nitrogen.params import NitrogenRateParams
from agrogame.soil.nutrients import EnvironmentalCache
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

# AC1: DSSAT-CSM PHFACT = AMIN1(1.0, 0.33*PH - 1.36), floored at 0.
FACTOR_TABLE = [
    (4.0, 0.0),
    (4.12, 0.0),
    (4.5, 0.125),
    (5.0, 0.29),
    (6.0, 0.62),
    (6.8, 0.884),
    (7.5, 1.0),
    (9.0, 1.0),
]
# Spans the Rousk response: 0 at 4.0, 2/3 at 4.5, plateau from 6.8.
PH_GRADIENT = [4.0, 5.0, 6.0]
NH4_KG_HA = 20.0


def _loam() -> SoilProfile:
    return load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]


def _standalone_cycle(
    *, self_mineralization: bool = False
) -> tuple[NitrogenCycle, EventBus]:
    """A profile-backed cycle with no water state: theta = field capacity."""
    profile = _loam()
    bus = EventBus()
    state = SoilNitrogenState(profile)
    state.nh4 = [NH4_KG_HA] * len(state.nh4)
    params = NitrogenRateParams(enable_self_mineralization=self_mineralization)
    return NitrogenCycle(bus, state, profile=profile, params=params), bus


def _activity_event(layer: int, ph: float, excl_ph: float) -> MicrobialActivityComputed:
    """An activity event whose pH-inclusive index is the one ``ph`` implies."""
    return MicrobialActivityComputed(
        layer=layer,
        activity_index=excl_ph * EnvironmentalResponses().ph_modifier(ph),
        activity_index_excl_ph=excl_ph,
        wfps=0.5,
        ph=ph,
        temperature_c=20.0,
    )


# --- AC1: the factor --------------------------------------------------------


@pytest.mark.parametrize(("ph", "expected"), FACTOR_TABLE)
def test_nitrification_ph_factor_is_the_dssat_line(ph: float, expected: float) -> None:
    cycle, _ = _standalone_cycle()
    assert cycle._nitrification_ph_factor(ph) == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("ph", [float("nan"), float("inf")])
def test_nitrification_ph_factor_rejects_non_finite_ph(ph: float) -> None:
    cycle, _ = _standalone_cycle()
    with pytest.raises(ValueError, match="finite"):
        cycle._nitrification_ph_factor(ph)


def test_nitrification_ph_factor_reads_params() -> None:
    profile = _loam()
    params = NitrogenRateParams(
        nitrification_ph_slope=0.5, nitrification_ph_intercept=-2.0
    )
    cycle = NitrogenCycle(
        EventBus(), SoilNitrogenState(profile), profile=profile, params=params
    )
    assert cycle._nitrification_ph_factor(5.0) == pytest.approx(0.5, abs=1e-12)


# --- AC2: the pH-free activity index ----------------------------------------


def _run_orchestrated(
    days: int, seasons: int, ph_override: list[float] | None
) -> list[list[MicrobialActivityComputed]]:
    """Step loam / maize / NL (seed 42); return the activity events per season.

    After every day, assert the nitrogen cycle's pH-free cache holds the
    clamped index of the day's last event for each layer.
    """
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    maize = crops.get_preset("maize", "netherlands_temperate")
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "netherlands_temperate"
    ]
    series = SyntheticWeatherGenerator(climate, seed=42).generate(
        days * seasons, date(2024, 4, 25)
    )
    orch = FullSimulationOrchestrator(
        _loam(), crop=maize, latitude_deg=climate.latitude_deg
    )
    out: list[list[MicrobialActivityComputed]] = []
    for season in range(seasons):
        if season:
            orch.harvest()
            orch.reset_crop(maize)  # clears the bus: subscribe per season
        events: list[MicrobialActivityComputed] = []
        orch.event_bus.subscribe(MicrobialActivityComputed, events.append)
        for rec in series.records[season * days : (season + 1) * days]:
            if ph_override is not None:
                orch.chem_state.ph[:] = ph_override
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
            cache = orch.n_cycle._env.microbe_activity_excl_ph_by_layer
            latest = {ev.layer: ev.activity_index_excl_ph for ev in events}
            assert latest, f"season {season + 1}: no activity events"
            for layer, value in latest.items():
                assert cache[layer] == max(0.0, min(1.0, value))
        out.append(events)
    return out


@pytest.mark.parametrize("ph_override", [None, PH_GRADIENT])
def test_activity_index_is_excl_ph_times_ph_modifier(
    ph_override: list[float] | None,
) -> None:
    """AC2(a): over 30 orchestrated days the two indices differ by pH only."""
    resp = EnvironmentalResponses()
    (events,) = _run_orchestrated(30, 1, ph_override)
    assert len(events) == 30 * 3
    for ev in events:
        expected = ev.activity_index_excl_ph * resp.ph_modifier(ev.ph)
        assert ev.activity_index == pytest.approx(expected, rel=1e-12, abs=0.0)
    if ph_override is not None:
        # Non-vacuous: the pH modifier bites in every layer, and in layer 0
        # (the day's proton budget lifts it to about pH 4.003) nearly zeroes
        # the pH-inclusive index while the pH-free one stays positive.
        for ev in events:
            assert ev.activity_index_excl_ph > 0.0
            assert resp.ph_modifier(ev.ph) < 0.9
        assert all(resp.ph_modifier(ev.ph) < 0.01 for ev in events if ev.layer == 0)


def test_excl_ph_cache_tracks_events_across_two_seasons() -> None:
    """The pH-free cache follows the events in both seasons of a reset (#558)."""
    seasons = _run_orchestrated(20, 2, PH_GRADIENT)
    assert [len(evs) for evs in seasons] == [20 * 3, 20 * 3]


def test_nitrification_ignores_heterotroph_ph_response() -> None:
    """AC2(b): equal pH-free activity nitrifies equally, whatever its pH."""
    cycle_acid, bus_acid = _standalone_cycle()
    cycle_neutral, bus_neutral = _standalone_cycle()
    n = len(cycle_acid.state.nh4)
    for layer in range(n):
        bus_acid.emit(_activity_event(layer, 5.0, 0.8))
        bus_neutral.emit(_activity_event(layer, 6.8, 0.8))
    # Non-vacuous: the pH-inclusive caches differ, by the Rousk factor at 5.0.
    acid_incl = cycle_acid._env.microbe_activity_by_layer
    assert acid_incl != cycle_neutral._env.microbe_activity_by_layer
    ph = [6.0] * n
    acid = cycle_acid.daily_step(temperature_c=20.0, ph_by_layer=ph)
    neutral = cycle_neutral.daily_step(temperature_c=20.0, ph_by_layer=ph)
    assert acid.nitrified_kg_ha > 0.0
    assert acid.nitrified_kg_ha == neutral.nitrified_kg_ha
    assert cycle_acid.state.nh4 == cycle_neutral.state.nh4


def test_mineralisation_keeps_heterotroph_ph_response() -> None:
    """Self-mineralisation still reads the pH-inclusive activity index."""
    cycle_acid, bus_acid = _standalone_cycle(self_mineralization=True)
    cycle_neutral, bus_neutral = _standalone_cycle(self_mineralization=True)
    n = len(cycle_acid.state.nh4)
    for layer in range(n):
        bus_acid.emit(_activity_event(layer, 5.0, 0.8))
        bus_neutral.emit(_activity_event(layer, 6.8, 0.8))
    ph = [6.0] * n
    acid = cycle_acid.daily_step(temperature_c=20.0, ph_by_layer=ph)
    neutral = cycle_neutral.daily_step(temperature_c=20.0, ph_by_layer=ph)
    ratio = acid.mineralized_kg_ha / neutral.mineralized_kg_ha
    assert ratio == pytest.approx(EnvironmentalResponses().ph_modifier(5.0), rel=1e-9)


# --- AC2: the cache ----------------------------------------------------------


def test_excl_ph_cache_clamps_and_starts_at_initial_activity() -> None:
    bus = EventBus()
    cache = EnvironmentalCache(bus, 3, initial_microbe_activity=0.9)
    assert cache.microbe_activity_excl_ph_by_layer == [0.9, 0.9, 0.9]
    bus.emit(_activity_event(0, 4.0, 2.5))
    bus.emit(_activity_event(1, 6.8, -0.1))
    bus.emit(_activity_event(9, 6.8, 0.3))  # out of range, ignored
    assert cache.microbe_activity_excl_ph_by_layer == [1.0, 0.0, 0.9]
    # pH 4.0 zeroes the pH-inclusive index, not the pH-free one.
    assert cache.microbe_activity_by_layer[0] == 0.0


def test_excl_ph_cache_is_declared_memory() -> None:
    """Saved and restored in place (#585); an older save keeps the initial."""
    bus = EventBus()
    cache = EnvironmentalCache(bus, 2)
    bus.emit(_activity_event(0, 5.0, 0.4))
    saved = cache.memory_to_dict()
    assert saved["microbe_activity_excl_ph_by_layer"] == [0.4, 1.0]

    restored = EnvironmentalCache(EventBus(), 2)
    alias = restored.microbe_activity_excl_ph_by_layer
    restored.restore_memory(saved)
    assert alias == [0.4, 1.0]
    assert restored.microbe_activity_excl_ph_by_layer is alias

    old_save = {
        k: v for k, v in saved.items() if k != "microbe_activity_excl_ph_by_layer"
    }
    from_old = EnvironmentalCache(EventBus(), 2)
    from_old.restore_memory(old_save)
    assert from_old.microbe_activity_excl_ph_by_layer == [1.0, 1.0]
    assert from_old.microbe_activity_by_layer == cache.microbe_activity_by_layer


# --- AC3: rate response ------------------------------------------------------


def _layer0_nitrified(ph: float) -> float:
    cycle, bus = _standalone_cycle()
    layer0: list[float] = []
    bus.subscribe(
        NitrificationOccurred,
        lambda ev: layer0.append(ev.amount_kg_ha) if ev.layer == 0 else None,
    )
    cycle.daily_step(temperature_c=20.0, ph_by_layer=[ph] * len(cycle.state.nh4))
    assert len(layer0) == 1
    return layer0[0]


@pytest.mark.parametrize("ph", [4.5, 5.0, 6.0, 6.8])
def test_layer0_rate_ratio_equals_factor(ph: float) -> None:
    """AC3: at 20 C and field capacity, rate(pH) / rate(7.5) is the factor."""
    cycle, _ = _standalone_cycle()
    ratio = _layer0_nitrified(ph) / _layer0_nitrified(7.5)
    assert ratio == pytest.approx(cycle._nitrification_ph_factor(ph), abs=1e-9)
    assert ratio == pytest.approx(dict(FACTOR_TABLE)[ph], abs=1e-9)
