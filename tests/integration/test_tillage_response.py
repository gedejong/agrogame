"""One tillage pass must not move two-season maize grain by more than 10 % (#526).

Root elongation used to read the topsoil mean weight diameter, so a moldboard
pass, which destroys macroaggregates, slowed rooting by 21-31 % and moved grain
by +15.6 % in season 1 and -30.0 % in season 2 on NL loam. Root elongation no
longer reads aggregate structure (ADR-021). The other tillage channels stay:
the pass still destroys macroaggregates, which still feed SOM protection and
the Ksat factor.

Setup (#526 B4): maize under ``netherlands_temperate`` on ``loam_temperate``
and ``clay_temperate``. Season 1 starts 2024-04-15 (seed 42) and season 2
2025-04-15 (seed 43), 150 days each, joined by ``harvest()`` then
``reset_crop``. Ammonium nitrate at 150 kg N/ha on day 0 of each season, after
any tillage pass. Arms: untilled; a moldboard pass (``apply_tillage(1.0)``) in
season 1 only; one in each season; and, on loam only, the client's Tillage
button (``apply_tillage(0.8)``) in each season.

The grain bound is on magnitude, not sign. Pittelkow et al. 2015b (Field Crops
Res. 183:156-168, doi:10.1016/j.fcr.2015.07.020) find maize under no-till
yields 7.6 % below conventional tillage, so a pass should cost nothing or gain
a few per cent. The engine models none of the mechanisms behind that
advantage (no bulk-density loosening, no residue or weed effects), so the
test does not assert a sign; it asserts that no pass moves grain by more than
10 %.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

_CLIMATE = "netherlands_temperate"
_SEASONS = ((date(2024, 4, 15), 42), (date(2025, 4, 15), 43))
_SEASON_DAYS = 150
_N_KG_HA = 150.0
# Arm -> (tillage intensity, seasons with a pass on day 0).
_ARMS: dict[str, tuple[float, tuple[int, ...]]] = {
    "untilled": (0.0, ()),
    "moldboard_s1": (1.0, (0,)),
    "moldboard_each": (1.0, (0, 1)),
    "client_button_each": (0.8, (0, 1)),
}
_TILLED = (
    ("loam_temperate", "moldboard_s1"),
    ("loam_temperate", "moldboard_each"),
    ("loam_temperate", "client_button_each"),
    ("clay_temperate", "moldboard_s1"),
    ("clay_temperate", "moldboard_each"),
)
_MOLDBOARD = tuple((s, a) for s, a in _TILLED if _ARMS[a][0] == 1.0)


@dataclass
class _Run:
    """What one two-season arm records."""

    depth_cm: list[list[float]] = field(default_factory=list)  # [season][day]
    grain_g_m2: list[float] = field(default_factory=list)  # day 150, per season
    macro0_pass: list[tuple[float, float]] = field(default_factory=list)
    mwd0_end_s1: float = 0.0


@cache
def _weather(start: date, seed: int) -> tuple[WeatherRecord, ...]:
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    generator = SyntheticWeatherGenerator(climates.climates[_CLIMATE], seed=seed)
    return tuple(generator.generate(_SEASON_DAYS, start).records)


@cache
def _run(soil: str, arm: str) -> _Run:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[_CLIMATE]
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", _CLIMATE
    )
    profile = load_soil_presets(Path("data/soils/presets.yaml")).soils[soil]
    orch = FullSimulationOrchestrator(
        profile, crop=crop, latitude_deg=climate.latitude_deg
    )
    intensity, tilled_seasons = _ARMS[arm]
    run = _Run()
    for season, (start, seed) in enumerate(_SEASONS):
        if season > 0:
            orch.harvest()
            orch.reset_crop(crop)
        if season in tilled_seasons:
            before = orch.agg_state.macro[0]
            orch.apply_tillage(intensity)
            run.macro0_pass.append((before, orch.agg_state.macro[0]))
        orch.apply_fertilizer("ammonium_nitrate", _N_KG_HA)
        depths: list[float] = []
        for rec in _weather(start, seed):
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
            depths.append(orch.root_state.current_depth_cm)
        run.depth_cm.append(depths)
        run.grain_g_m2.append(orch.canopy.state.grain_biomass_g_m2)
        if season == 0:
            run.mwd0_end_s1 = orch.agg_state.mwd(0)
    return run


@pytest.mark.parametrize(("soil", "arm"), _TILLED)
def test_tillage_leaves_root_depth_unchanged(soil: str, arm: str) -> None:
    """(a) Root depth is the untilled arm's on every day of both seasons.

    Tillage loosens the plough layer (Lampurlanés & Cantero-Martínez 2003,
    Agron. J. 95:526-536), and root growth differs little between tillage
    systems, so a pass must not slow the root front.
    """
    tilled, untilled = _run(soil, arm), _run(soil, "untilled")
    assert max(untilled.depth_cm[1]) > 0.0
    for season in (0, 1):
        pairs = zip(tilled.depth_cm[season], untilled.depth_cm[season], strict=True)
        for day, (got, want) in enumerate(pairs):
            assert abs(got - want) <= 1e-9, (
                f"{soil} {arm} S{season + 1} day {day}: root depth {got:.3f} cm, "
                f"untilled {want:.3f} cm"
            )


@pytest.mark.parametrize("season", (0, 1))
@pytest.mark.parametrize(("soil", "arm"), _TILLED)
def test_tillage_moves_grain_by_at_most_ten_percent(
    soil: str, arm: str, season: int
) -> None:
    """(b) |grain_tilled / grain_untilled - 1| <= 0.10 at day 150 of each season.

    The bound is on magnitude, not sign (Pittelkow et al. 2015b; see the module
    docstring).
    """
    untilled = _run(soil, "untilled").grain_g_m2[season]
    tilled = _run(soil, arm).grain_g_m2[season]
    assert untilled > 0.0, f"{soil} S{season + 1}: untilled arm set no grain"
    change = tilled / untilled - 1.0
    assert abs(change) <= 0.10, (
        f"{soil} {arm} S{season + 1}: grain {tilled:.1f} vs untilled "
        f"{untilled:.1f} g/m2 ({change:+.2%})"
    )


@pytest.mark.parametrize(("soil", "arm"), _MOLDBOARD)
def test_moldboard_pass_still_destroys_topsoil_macroaggregates(
    soil: str, arm: str
) -> None:
    """(c) Each pass leaves 30 % of layer-0 macroaggregates; S1 ends with lower MWD.

    A moldboard pass reaches the whole top layer and destroys 70 % of its
    macroaggregates, the top of the 30-70 % range (Six et al. 2000, SSSAJ)
    that ``SoilAggregationParams`` cites.
    """
    run = _run(soil, arm)
    assert len(run.macro0_pass) == len(_ARMS[arm][1])
    for before, after in run.macro0_pass:
        assert abs(after - 0.30 * before) <= 1e-9, f"{soil} {arm}: {before} -> {after}"
    assert run.mwd0_end_s1 < _run(soil, "untilled").mwd0_end_s1
