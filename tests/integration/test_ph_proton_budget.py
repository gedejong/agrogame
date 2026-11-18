"""Soil pH follows the N-cycle proton budget, not a clock (#492, ADR-020).

Before #492 layer-0 pH ended a 150-day season at 6.521287 in every run, to six
decimals, whatever the soil, N rate or rain: a fixed -0.002/day P-fixation
proxy did all of it. Now pH moves only with the H+ the N transformations
release, through each layer's pH buffer capacity (Bolan, Hedley & White 1991,
Plant Soil 134:53-63; Helyar & Porter 1989). The magnitude band is anchored on
Goulding 2016 (Soil Use Manage. 32:390-399): urea-N needs about 100-200 kg
CaCO3/ha per 50 kg N, i.e. 0.56-1.1 mol H+ per mol N over a full year
including product removal, widened at the low end for a 150-day season that
ends with N still in the soil.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import pytest

from agrogame.game.field import FieldManager, PatchConfig
from agrogame.plant.presets import CropPreset, load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.chemistry.module import SoilChemistryModule
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen.constants import N_KG_PER_KMOL
from agrogame.soil.nitrogen.events import ProtonLoadOccurred
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

_HAS_API = bool(
    importlib.util.find_spec("fastapi") and importlib.util.find_spec("httpx")
)
_SEASON_DAYS = 150
_UREA_SPLIT = {0: 0.4, 30: 0.3, 60: 0.3}  # share of the season N on that day


# --- AC6: behaviour through the API ------------------------------------------


@dataclass(frozen=True)
class _Season:
    """Layer-0 outcome of one 150-day API season."""

    ph_start: float
    ph_end: float
    layer0_h_kmol_ha: float  # net H+ released into layer 0 over the season

    @property
    def dph(self) -> float:
        return self.ph_end - self.ph_start


def _api_season(
    soil: str, n_total: float, rain_mult: float = 1.0, seed: int = 42
) -> _Season:
    """Maize, netherlands_temperate, urea 40/30/30 on days 0/30/60, 150 days."""
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.routes import _ensure_weather
    from agrogame.api.state import games

    client = TestClient(create_app())
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": [
                {
                    "field_id": "f1",
                    "patches": [
                        {
                            "soil_profile_key": soil,
                            "crop_key": "maize",
                            "climate_key": "netherlands_temperate",
                            "area_fraction": 1.0,
                        }
                    ],
                }
            ],
            "starting_credits": 10_000_000,
        },
    )
    assert resp.status_code == 200
    game_id = resp.json()["game_id"]
    session = games[game_id]
    orch = session.field_manager.fields["f1"].patches[0].orch
    # The season's weather, scaled before the first step when rain is varied.
    _ensure_weather(session, seed)
    session.weather = [
        replace(r, precip_mm=(r.precip_mm or 0.0) * rain_mult) for r in session.weather
    ]
    layer0_h: list[float] = []

    def _record(ev: ProtonLoadOccurred) -> None:
        if ev.layer == 0:
            layer0_h.append(ev.h_kmol_ha)

    orch.event_bus.subscribe(ProtonLoadOccurred, _record)
    ph_start = orch.chem.ph_by_layer[0]
    for day in range(_SEASON_DAYS):
        share = _UREA_SPLIT.get(day, 0.0)
        if n_total > 0.0 and share > 0.0:
            action = client.post(
                f"/api/v1/games/{game_id}/action",
                json={
                    "field_id": "f1",
                    "action": "fertilize",
                    "params": {"type": "urea", "amount_kg_ha": n_total * share},
                },
            )
            assert action.status_code == 200
        step = client.post(f"/api/v1/games/{game_id}/step?days=1&seed={seed}")
        assert step.status_code == 200
    out = _Season(ph_start, orch.chem.ph_by_layer[0], sum(layer0_h))
    del games[game_id]
    return out


@pytest.fixture(scope="module")
def seasons() -> dict[tuple[str, float, float], _Season]:
    """The AC6 matrix, run once: (soil, kg N/ha, rain multiplier) -> season."""
    if not _HAS_API:
        pytest.skip("fastapi or httpx not installed")
    runs = [("loam_temperate", n, 1.0) for n in (0.0, 100.0, 200.0, 250.0)]
    runs += [("clay_temperate", 250.0, 1.0), ("sandy_temperate", 250.0, 1.0)]
    runs += [("loam_temperate", 200.0, 2.0)]
    return {run: _api_season(*run) for run in runs}


def test_n_ordering(seasons: dict[tuple[str, float, float], _Season]) -> None:
    """AC6(a): layer-0 dpH at 0 > 100 > 200 > 250 kg N, strictly."""
    dph = [seasons[("loam_temperate", n, 1.0)].dph for n in (0.0, 100.0, 200.0, 250.0)]
    assert dph[0] > dph[1] > dph[2] > dph[3], dph


def test_no_n_no_drift(seasons: dict[tuple[str, float, float], _Season]) -> None:
    """AC6(b): |dpH| <= 0.005 at 0 kg N (the old clock gave -0.279)."""
    assert abs(seasons[("loam_temperate", 0.0, 1.0)].dph) <= 0.005


def test_clay_buffers_more_than_sand(
    seasons: dict[tuple[str, float, float], _Season],
) -> None:
    """AC6(c): at 250 kg N, |dpH| on clay_temperate < sandy_temperate."""
    clay = seasons[("clay_temperate", 250.0, 1.0)].dph
    sand = seasons[("sandy_temperate", 250.0, 1.0)].dph
    assert abs(clay) < abs(sand), (clay, sand)


def test_wet_season_acidifies_at_least_as_much(
    seasons: dict[tuple[str, float, float], _Season],
) -> None:
    """AC6(d): at 200 kg N, rainfall x2 acidifies layer 0 at least as much."""
    dry = seasons[("loam_temperate", 200.0, 1.0)].dph
    wet = seasons[("loam_temperate", 200.0, 2.0)].dph
    assert wet <= dry, (wet, dry)


def test_magnitude_in_goulding_band(
    seasons: dict[tuple[str, float, float], _Season],
) -> None:
    """AC6(e): at 200 kg N, 0.25-1.1 mol H+ per mol N; dpH in [-0.10, -0.02]."""
    run = seasons[("loam_temperate", 200.0, 1.0)]
    applied_kmol_n = 200.0 / N_KG_PER_KMOL
    assert 0.25 <= run.layer0_h_kmol_ha / applied_kmol_n <= 1.1
    assert -0.10 <= run.dph <= -0.02


# --- Orchestrator harnesses (AC10, AC12) -------------------------------------


def _maize() -> CropPreset:
    return load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", "netherlands_temperate"
    )


def _orchestrator() -> FullSimulationOrchestrator:
    profile = load_soil_presets(Path("data/soils/presets.yaml")).soils["loam_temperate"]
    return FullSimulationOrchestrator(profile, crop=_maize(), latitude_deg=52.0)


def _step(orch: FullSimulationOrchestrator, rain_mm: float = 2.0) -> None:
    orch.step_day(
        DailyDrivers(rainfall_mm=rain_mm),
        tmin_c=10.0,
        tmax_c=22.0,
        shortwave_mj_m2=15.0,
        sim_date=date(2024, 5, 1),
    )


def test_no_protons_pending_after_any_step_across_two_seasons() -> None:
    """AC12(i): every step releases its H+, SOM ammonification included.

    SOM mineralises after the N cycle's own nutrients-phase step, so a release
    at the end of NitrogenCycle.daily_step would carry it to the next day.
    """
    orch = _orchestrator()
    maize = _maize()
    som_days = 0
    for season in range(2):
        if season:
            orch.harvest()
            orch.reset_crop(maize)
        released: list[ProtonLoadOccurred] = []
        orch.event_bus.subscribe(ProtonLoadOccurred, released.append)
        orch.apply_fertilizer("urea", 60.0)
        for _ in range(30):
            _step(orch)
            assert orch.n_cycle.pending_proton_load_kmol_ha == [0.0] * len(
                orch.profile.layers
            )
            if orch.n_cycle.som_mineralized_n_total > 0.0:
                som_days += 1
        assert released, f"season {season + 1}: no proton load released"
    assert som_days >= 50  # SOM is active, so its term is exercised


def _chemistry_loads(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, float]]:
    """Record every (layer, H+) the chemistry module receives, across rebuilds."""
    calls: list[tuple[int, float]] = []
    original = SoilChemistryModule.apply_proton_load

    def _spy(self: SoilChemistryModule, layer: int, h_kmol_ha: float) -> None:
        calls.append((layer, h_kmol_ha))
        original(self, layer, h_kmol_ha)

    monkeypatch.setattr(SoilChemistryModule, "apply_proton_load", _spy)
    return calls


def test_urea_hydrolysis_reaches_chemistry_once_across_reset_crop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC12(ii): urea, then reset_crop before the next step: counted once.

    ``reset_crop`` rebuilds the N cycle, so a hydrolysis term held for the
    next day_end would be lost. The control applies the same urea without the
    reset: both must deliver the same H+ and end at the same pH.
    """
    calls = _chemistry_loads(monkeypatch)
    urea_h = -100.0 / N_KG_PER_KMOL
    results = []
    for reset in (False, True):
        calls.clear()
        orch = _orchestrator()
        orch.apply_fertilizer("urea", 100.0)
        assert calls == [(0, pytest.approx(urea_h, abs=1e-12))]
        assert orch.n_cycle.pending_proton_load_kmol_ha[0] == 0.0
        if reset:
            orch.reset_crop(_maize())
        _step(orch)
        urea_terms = [h for layer, h in calls if layer == 0 and abs(h - urea_h) < 1e-9]
        assert len(urea_terms) == 1
        results.append((list(calls), orch.chem.ph_by_layer))
    (control_calls, control_ph), (reset_calls, reset_ph) = results
    assert [layer for layer, _ in reset_calls] == [layer for layer, _ in control_calls]
    assert [h for _, h in reset_calls] == pytest.approx(
        [h for _, h in control_calls], abs=1e-12
    )
    assert reset_ph == pytest.approx(control_ph, abs=1e-12)


def _patch_manager() -> FieldManager:
    fm = FieldManager()
    fm.add_field(
        "f1", [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]
    )
    return fm


def _fm_days(fm: FieldManager, days: range) -> None:
    for day in days:
        fm.step_day(
            drivers=DailyDrivers(rainfall_mm=3.0 if day % 4 == 0 else 0.0),
            tmin_c=9.0,
            tmax_c=21.0,
            shortwave_mj_m2=16.0,
            sim_date=date(2024, 4, 1),
        )


def test_save_between_urea_and_step_continues_exactly() -> None:
    """#577 exact continuation, at the point the release timing protects.

    Urea's hydrolysis H+ is released at application, so a save taken before
    the next step carries it in the saved pH, and the declared budget memory
    (``NitrogenCycle._pending_h_kmol_ha``) is empty at every save point.
    """
    reference = _patch_manager()
    _fm_days(reference, range(20))
    reference.fields["f1"].apply_fertilizer("urea", 80.0)
    saved = json.loads(json.dumps(reference.to_dict()))
    memory = saved["fields"]["f1"]["patches"][0]["runtime_memory"]
    n_layers = len(reference.fields["f1"].patches[0].orch.profile.layers)
    assert memory["NitrogenCycle"]["_pending_h_kmol_ha"] == [0.0] * n_layers
    loaded = FieldManager.from_dict(saved)
    for fm in (reference, loaded):
        _fm_days(fm, range(20, 60))
    ref_orch = reference.fields["f1"].patches[0].orch
    got_orch = loaded.fields["f1"].patches[0].orch
    assert got_orch.chem.ph_by_layer == ref_orch.chem.ph_by_layer
    assert got_orch.n_state.no3 == ref_orch.n_state.no3
    assert (
        got_orch.canopy.state.grain_biomass_g_m2
        == ref_orch.canopy.state.grain_biomass_g_m2
    )
    # The budget moved pH (hydrolysis alkalinises first, nitrification follows).
    assert abs(ref_orch.chem.ph_by_layer[0] - 6.8) > 1e-3


def _calendar_years(seed: int, years: int = 3) -> Iterator[float]:
    """AC10 harness: layer-0 pH at each year end (#481's calendar-year harness).

    loam_temperate, maize, netherlands_temperate, 365-day years from 25 April;
    harvest() + reset_crop(None) at day 180; reset_crop(maize) on day 0 of
    later years; urea 80/60/60 kg N/ha on days 0/30/60 after sowing.
    """
    maize = _maize()
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "netherlands_temperate"
    ]
    start = date(2024, 4, 25)
    records = SyntheticWeatherGenerator(climate, seed=seed).generate(years * 365, start)
    orch = FullSimulationOrchestrator(
        load_soil_presets(Path("data/soils/presets.yaml")).soils["loam_temperate"],
        crop=maize,
        latitude_deg=climate.latitude_deg,
    )
    urea = {0: 80.0, 30: 60.0, 60: 60.0}
    for year in range(years):
        for day in range(365):
            if day == 0 and year > 0:
                orch.reset_crop(maize)
            if day == 180:
                orch.harvest()
                orch.reset_crop(None)
            if day in urea:
                orch.apply_fertilizer("urea", urea[day])
            rec = records.records[year * 365 + day]
            orch.step_day(
                DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
        yield orch.chem.ph_by_layer[0]


def test_three_year_trajectory_follows_n_management() -> None:
    """AC10: pH falls year on year and carries across reset_crop.

    Bounds from the 2026-11-18 refinement prototype (6.770 / 6.741 / 6.722;
    seed 43: 6.767 / 6.743 / 6.725). The old clock gave 6.19 / 5.76 / 5.47.
    """
    ph = list(_calendar_years(seed=42))
    assert ph[0] > ph[1] > ph[2], ph
    assert 6.74 <= ph[0] <= 6.80, ph
    assert 6.68 <= ph[2] <= 6.75, ph
    assert min(ph) >= 6.5, ph
