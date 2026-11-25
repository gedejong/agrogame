"""The 5-Day Outlook against the engine, through ``GET /forecast`` (#689).

Seeds 42-51, the default 200-day season from 2024-04-01, no actions, patch 0 of
every field. On each day the forecast is taken from the state the step left,
and its rows are compared with the engine on the dates they project, on
standing days (emerged to grain fill). As in the #689 refinement:

- C4: the projected root-zone fraction against the Root zone gauge
  (``root_zone_water_fraction``), both capped at 1, in gauge points;
- C5: ``water_stress`` (the projected Ta/Tp) against the engine's Ks, the last
  ``WaterStressComputed.stress`` of the day, which the Water gauge reads;
- C8: the direction of row 5's mineral N against the engine's root-zone N, on
  anchors where the engine moves by more than 1 kg/ha over the 5 days.

A magnitude is the median over seeds of each seed's median (#615 policy d).
"""

from __future__ import annotations

import statistics
from functools import cache
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.forecast import project_soil_forecast  # noqa: E402
from agrogame.api.routes import (  # noqa: E402
    _project_patch,
    _projection_inputs,
    _root_zone_water_fraction,
)
from agrogame.api.state import games  # noqa: E402

SEEDS = range(42, 52)
SEASON = 200
HORIZON = 5
STANDING = frozenset({"emerged", "vegetative", "flowering", "grain_fill"})
_CLIENT = TestClient(create_app())
# (field label, soil, crop, climate); fields sharing a climate share one game.
FIELDS = {
    "nl_maize": ("sandy_temperate", "maize", "netherlands_temperate"),
    "kenya_maize": ("loam_temperate", "maize", "kenya_highlands"),
    "kenya_wheat": ("clay_temperate", "spring_wheat", "kenya_highlands"),
    "sahel_sorghum": ("sandy_subsaharan", "sorghum", "sahel_arid"),
}
# C4 row-5 bound per field, gauge points (refinement C4).
ROW5_BOUND = {"nl_maize": 3.0, "kenya_maize": 3.0, "kenya_wheat": 3.0}


def _new_game(labels: list[str]) -> str:
    fields = [
        {
            "field_id": label,
            "patches": [
                {
                    "soil_profile_key": FIELDS[label][0],
                    "crop_key": FIELDS[label][1],
                    "climate_key": FIELDS[label][2],
                    "area_fraction": 1.0,
                }
            ],
        }
        for label in labels
    ]
    resp = _CLIENT.post("/api/v1/games", json={"fields": fields})
    assert resp.status_code == 200, resp.text
    gid: str = resp.json()["game_id"]
    return gid


def _root_zone_n(orch: Any) -> float:
    """Engine root-zone NO3 + NH4 (kg/ha) at the current root depth."""
    top, total = 0.0, 0.0
    for i, layer in enumerate(orch.profile.layers):
        rooted = (orch.root_state.current_depth_cm - top) / layer.depth_cm
        total += (orch.n_state.no3[i] + orch.n_state.nh4[i]) * min(
            1.0, max(0.0, rooted)
        )
        top += layer.depth_cm
    return total


def _ks(patch: dict[str, Any]) -> float:
    stresses = [
        e["data"]["stress"]
        for e in patch["events"]
        if e["event_type"] == "WaterStressComputed"
    ]
    return float(stresses[-1]) if stresses else 1.0


@cache
def _run(labels: tuple[str, ...], seed: int) -> dict[str, dict[str, list]]:
    """Per field: the anchors (day, engine N, rows, fractions) and engine days."""
    games.clear()
    gid = _new_game(list(labels))
    s = games[gid]
    out: dict[str, dict[str, list]] = {f: {"anchors": [], "engine": []} for f in labels}
    for day in range(SEASON):
        for fid in labels:
            patch = s.field_manager.fields[fid].patches[0]
            if patch.orch.is_fallow:
                continue
            url = f"/api/v1/games/{gid}/forecast?field_id={fid}&seed={seed}"
            rows = _CLIENT.get(url).json()["forecast"]
            # The first GET generates the season's weather.
            window = s.weather[s.day_index : s.day_index + HORIZON]
            fractions = [
                p.root_zone_water_fraction for p in _project_patch(s, patch, window)
            ]
            out[fid]["anchors"].append((day, _root_zone_n(patch.orch), rows, fractions))
        reply = _CLIENT.post(f"/api/v1/games/{gid}/step?days=1&seed={seed}").json()
        for fid in labels:
            p0 = reply["patches"][fid][0]
            orch = s.field_manager.fields[fid].patches[0].orch
            out[fid]["engine"].append(
                (
                    p0["crop_stage"],
                    min(1.0, p0["root_zone_water_fraction"]),
                    _ks(p0),
                    _root_zone_n(orch),
                )
            )
    return out


@cache
def _per_seed() -> dict[str, dict[str, list[float]]]:
    """Per field, per-seed metrics: C4 rows 1 and 5, C5 zero rows and |W-Ks|, C8."""
    games_by_climate: dict[str, list[str]] = {}
    for label, (_soil, _crop, climate) in FIELDS.items():
        games_by_climate.setdefault(climate, []).append(label)
    metrics: dict[str, dict[str, list[float]]] = {
        f: {"rz1": [], "rz5": [], "w0": [], "w5": [], "sign": []} for f in FIELDS
    }
    for labels in games_by_climate.values():
        for seed in SEEDS:
            for fid, run in _run(tuple(labels), seed).items():
                _score(run, metrics[fid])
    return metrics


def _score(run: dict[str, list], m: dict[str, list[float]]) -> None:
    engine = run["engine"]
    rz: dict[int, list[float]] = {1: [], 5: []}
    w5, zero_rows, agree = [], 0, []
    for day, anchor_n, rows, fractions in run["anchors"]:
        for h, (row, frac) in enumerate(zip(rows, fractions, strict=True), start=1):
            stage, rzf, ks, _n = engine[day + h - 1]
            if stage not in STANDING:
                continue
            if h in rz:
                rz[h].append(abs(100.0 * min(1.0, frac) - 100.0 * rzf))
            zero_rows += int(row["water_stress"] <= 0.005 and ks >= 0.70)
            if h == HORIZON:
                w5.append(abs(100.0 * row["water_stress"] - 100.0 * ks))
        if len(rows) == HORIZON and engine[day + HORIZON - 1][0] in STANDING:
            moved = engine[day + HORIZON - 1][3] - anchor_n
            if abs(moved) > 1.0:
                agree.append((rows[-1]["mineral_n_kg_ha"] > anchor_n) == (moved > 0))
    m["rz1"].append(statistics.median(rz[1]))
    m["rz5"].append(statistics.median(rz[5]))
    m["w0"].append(float(zero_rows))
    m["w5"].append(statistics.median(w5))
    if agree:
        m["sign"].append(100.0 * sum(agree) / len(agree))


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_c4_root_zone_fraction_tracks_the_gauge(field: str) -> None:
    m = _per_seed()[field]
    row1, row5 = statistics.median(m["rz1"]), statistics.median(m["rz5"])
    print(f"{field}: |root zone| row 1 {row1:.2f}, row 5 {row5:.2f} points")
    assert row1 <= 1.5
    assert row5 <= ROW5_BOUND.get(field, 6.0)


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_c5_water_stress_tracks_the_engines_ks(field: str) -> None:
    m = _per_seed()[field]
    w5 = statistics.median(m["w5"])
    print(f"{field}: W0 rows per seed {m['w0']}, |W-Ks| row 5 {w5:.2f} points")
    assert m["w0"] == [0.0] * len(SEEDS)
    assert w5 <= 6.0


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_c8_mineral_n_moves_with_the_engine(field: str) -> None:
    m = _per_seed()[field]
    share = statistics.median(m["sign"])
    print(f"{field}: N sign agreement {share:.0f} % over {len(m['sign'])} seeds")
    assert share >= 90.0


def _nl_game() -> tuple[Any, str]:
    """A fresh NL sandy maize game: the session and its id."""
    games.clear()
    gid = _new_game(["nl_maize"])
    return games[gid], gid


def _step(gid: str, days: int) -> dict[str, Any]:
    reply: dict[str, Any] = _CLIENT.post(
        f"/api/v1/games/{gid}/step?days={days}&seed=42"
    ).json()
    return reply


def test_c7_source_and_uptake_are_the_engines_anchor_day_fluxes() -> None:
    s, gid = _nl_game()
    reply = _step(gid, 40)
    patch = s.field_manager.fields["nl_maize"].patches[0]
    orch = patch.orch
    inputs = _projection_inputs(patch)
    top, source = 0.0, 0.0
    for flux, layer in zip(
        orch.n_cycle.som_mineralized_n_by_layer, orch.profile.layers, strict=True
    ):
        rooted = (orch.root_state.current_depth_cm - top) / layer.depth_cm
        source += flux * min(1.0, max(0.0, rooted))
        top += layer.depth_cm
    uptake = [
        e["data"]["uptake_kg_ha"]
        for e in reply["patches"]["nl_maize"][0]["events"]
        if e["event_type"] == "PlantNUptakeComputed"
    ]
    assert source > 0.0 and uptake[-1] > 0.0
    assert inputs.som_mineralization_kg_ha_day == pytest.approx(source, rel=1e-12)
    assert inputs.plant_n_uptake_kg_ha_day == uptake[-1]


def test_c3_crop_p_and_a_zero_et_hold_read_the_gauge() -> None:
    s, gid = _nl_game()
    patch = s.field_manager.fields["nl_maize"].patches[0]
    gauges = []
    for _ in range(8):
        _step(gid, 10)
        inputs = _projection_inputs(patch)
        assert inputs.depletion_fraction_p == 0.55  # maize, FAO-56 Table 22
        gauge = _root_zone_water_fraction(patch, list(patch.orch.water_state.theta))
        held = project_soil_forecast(weather=[(18.0, 0.0, 0.0)] * 5, **vars(inputs))
        assert [p.root_zone_water_fraction for p in held] == [min(1.0, gauge)] * 5
        gauges.append(gauge)
    print("gauge at the anchors", gauges)
    assert min(gauges) < 1.0
