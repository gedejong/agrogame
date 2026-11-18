"""Harvest leaves a bare patch (#538).

Each API session is mirrored by a control ``FieldManager`` built from the same
patches and stepped on the session's own weather, as ``_run_day_step`` does. A
harvest in the control is ``harvest(); Patch.reset_crop(None)``, and a plant is
``Patch.reset_crop(preset)``.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.state import games  # noqa: E402
from agrogame.game.economy import PriceTable  # noqa: E402
from agrogame.game.field import FieldManager, PatchConfig  # noqa: E402
from agrogame.plant.presets import load_crop_presets  # noqa: E402
from agrogame.soil.water.types import DailyDrivers  # noqa: E402

CLIMATE = "netherlands_temperate"
SOILS = (
    ("sandy_temperate", 0.333),
    ("loam_temperate", 0.334),
    ("clay_temperate", 0.333),
)
STATE_KEYS = ("soil_snapshot", "canopy_state", "phenology_state", "root_state")
STATE_KEYS += ("plant_n_state", "day_counter")


class Run:
    """An API game on the default scenario, plus its control FieldManagers."""

    def __init__(self, season_days: int, controls: int = 1) -> None:
        self.client = TestClient(create_app())
        patches = [
            {
                "soil_profile_key": s,
                "crop_key": "maize",
                "climate_key": CLIMATE,
                "area_fraction": a,
            }
            for s, a in SOILS
        ]
        fields = [{"field_id": "f1", "patches": patches}]
        resp = self.client.post("/api/v1/games", json={"fields": fields})
        self.gid = resp.json()["game_id"]
        games[self.gid].season_days = season_days
        self.day = 0
        self.ctl: list[FieldManager] = []
        for _ in range(controls):
            fm = FieldManager()
            fm.add_field("f1", [PatchConfig(s, "maize", CLIMATE, a) for s, a in SOILS])
            self.ctl.append(fm)

    def step(self, days: int) -> dict[str, Any]:
        resp = self.client.post(f"/api/v1/games/{self.gid}/step?days={days}")
        assert resp.status_code == 200, resp.text
        for rec in games[self.gid].weather[self.day : self.day + days]:
            for fm in self.ctl:
                fm.step_day(
                    drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                    tmin_c=rec.tmin_c,
                    tmax_c=rec.tmax_c,
                    shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                    sim_date=rec.day,
                )
        self.day += days
        return dict(resp.json())

    def act(self, action: str, crop_key: str = "maize") -> dict[str, Any]:
        """Act on patch 0 in the API session and in the first control."""
        params = {"patch_idx": 0, "crop_key": crop_key}
        body = {"field_id": "f1", "action": action, "params": params}
        resp = self.client.post(f"/api/v1/games/{self.gid}/action", json=body)
        assert resp.json()["status"] == "executed", resp.text
        patch = self.ctl[0].fields["f1"].patches[0]
        if action == "harvest":
            patch.harvest()
            patch.reset_crop(None)
        else:
            patch.reset_crop(load_crop_presets().get_preset(crop_key, CLIMATE))
        return dict(resp.json())

    def patch(self, i: int, fm: FieldManager | None = None) -> Any:
        fm = games[self.gid].field_manager if fm is None else fm
        return fm.fields["f1"].patches[i]

    def state(self, i: int, fm: FieldManager | None = None) -> dict[str, Any]:
        full = self.patch(i, fm).to_dict()
        return {k: full[k] for k in STATE_KEYS}


def test_harvested_patch_evolves_as_the_reset_control() -> None:
    """AC1-AC3: 100 days after a day-150 harvest of patch 0."""
    run = Run(season_days=250, controls=2)
    reset_ctl, no_harvest = run.ctl
    run.step(150)
    assert all(run.state(i) == run.state(i, no_harvest) for i in range(3))
    run.act("harvest")
    # AC2: the harvested crop's roots are gone. A bare patch has none (#542).
    assert run.patch(0).orch.root_state.current_depth_cm == 0.0
    for days in (1, 9, 40, 50):
        run.step(days)
        assert run.state(0) == run.state(0, reset_ctl), f"day {run.day}"  # AC1
        depth = run.patch(0).orch.root_state.current_depth_cm
        assert depth < run.patch(0, no_harvest).orch.root_state.current_depth_cm
        for i in (1, 2):  # AC3: non-targeted patches are bit-identical
            assert run.state(i) == run.state(i, no_harvest), f"patch {i}"


def _within_a1(a: Any, b: Any) -> None:
    """A1's (#515) continuation bounds between two patches."""
    oa, ob = a.orch, b.orch
    sa, sb = oa.snapshot_soil(), ob.snapshot_soil()
    for name in ("som_labile_c", "som_intermediate_c", "som_stable_c"):
        assert sum(getattr(sa, name)) == pytest.approx(sum(getattr(sb, name)), rel=1e-3)
    assert sum(sa.n_no3) == pytest.approx(sum(sb.n_no3), abs=1.0)
    rd = (oa.root_state.current_depth_cm, ob.root_state.current_depth_cm)
    assert rd[0] == pytest.approx(rd[1], rel=5e-3)
    n_stock = (oa.plant_n_stock_kg_ha, ob.plant_n_stock_kg_ha)
    assert n_stock[0] == pytest.approx(n_stock[1], rel=0.05, abs=1e-6)
    for name in ("grain_biomass_g_m2", "biomass_g_m2"):
        pair = (getattr(oa.canopy.state, name), getattr(ob.canopy.state, name))
        assert pair[0] == pytest.approx(pair[1], rel=0.02, abs=1e-6)


def test_two_cycles_harvest_fallow_plant_harvest(tmp_path, monkeypatch) -> None:
    """AC4, AC5, the stage mask, and the multi-cycle rule on patch 0."""
    import agrogame.api.routes as routes

    monkeypatch.setattr(routes, "_SAVE_DIR", tmp_path)
    run = Run(season_days=301)
    for cycle in (1, 2):
        grown = run.step(120 if cycle == 1 else 100)
        assert grown["patches"]["f1"][0]["root_depth_cm"] > 5.0
        grain = run.patch(0).orch.canopy.state.grain_biomass_g_m2
        harvest = run.act("harvest")
        assert run.state(0) == run.state(0, run.ctl[0]), f"cycle {cycle}"
        # AC4: the response is settled from the pre-reset crop (day 120 is Q3),
        # using the route's area-weighted mean over the one harvested patch.
        assert harvest["grain_g_m2"] == round(grain, 1)
        if cycle == 1:
            price = PriceTable.load().get_crop_price("maize", 3)
            mean = grain * 0.333 / 0.333
            assert grain > 0.0
            assert harvest["revenue_credits"] == int(mean * 10.0 * 0.333 * price)
        else:  # AC5: save and load right after a harvest
            assert run.client.post(f"/api/v1/games/{run.gid}/save").is_success
            assert run.client.post(f"/api/v1/games/{run.gid}/load").is_success
        fallow = run.step(20)
        bare = [d for d in fallow["daily_snapshots"] if d["patch_idx"] == 0]
        assert {(d["crop_stage"], d["dev_stage"]) for d in bare} == {("", 0.0)}
        assert fallow["patches"]["f1"][0]["crop_stage"] == ""
        assert fallow["patches"]["f1"][1]["crop_stage"] != ""
        if cycle == 1:
            assert run.state(0) == run.state(0, run.ctl[0])
            run.act("plant")
            planted = run.step(1)["patches"]["f1"][0]
            assert planted["crop_stage"] == "planted" and planted["events"]
    run.step(40)
    for i in range(3):
        _within_a1(run.patch(i), run.patch(i, run.ctl[0]))


# #542: the plant events, and the plant-stress events the client draws as a
# crop icon (stress_icons.gd, farm_view.gd). A bare patch emits neither.
PLANT_EVENTS = frozenset(
    "StageChanged GddAccumulated RootDepthChanged RootDistributionUpdated "
    "RootBiomassUpdated RootTurnoverOccurred BiomassAccumulated LAIUpdated "
    "LightIntercepted FrostDamageApplied HeatDamageApplied WaterStressComputed "
    "NutrientStressComputed".split()
)


def test_bare_patch_reports_no_plant() -> None:
    """#542 AC7: stage, roots, LAI, events and forecast of a harvested patch."""
    from agrogame.api.routes import _projection_inputs

    run = Run(season_days=150)
    run.step(110)
    run.act("harvest")
    for _ in range(30):
        resp = run.step(1)
        bare = [d for d in resp["daily_snapshots"] if d["patch_idx"] == 0]
        p0 = resp["patches"]["f1"][0]
        assert len(bare) == 1 and p0["root_depth_cm"] == 0.0
        for rec in (*bare, p0):
            assert (rec["crop_stage"], rec["dev_stage"], rec["lai"]) == ("", 0.0, 0.0)
            assert rec["events"]
            assert not {e["event_type"] for e in rec["events"]} & PLANT_EVENTS
        assert resp["patches"]["f1"][1]["crop_stage"] != ""
        inputs = _projection_inputs(run.patch(0))
        assert (inputs.root_depth_cm, inputs.root_growth_rate_cm_per_day) == (0, 0)
        forecast = run.client.get(f"/api/v1/games/{run.gid}/forecast").json()
        days = forecast["forecast"]
        assert {(d["mineral_n_kg_ha"], d["water_stress"]) for d in days} == {(0, 1)}
