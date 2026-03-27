"""Tests for management plan auto-scheduling (AGRO-101)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _make_orch(
    plan: ManagementPlan | None = None,
) -> FullSimulationOrchestrator:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    climate = climates.climates["netherlands_temperate"]
    return FullSimulationOrchestrator(
        profile,
        crop=crops.crops["maize"],
        latitude_deg=climate.latitude_deg,
        management_plan=plan,
    )


def _step_days(orch: FullSimulationOrchestrator, n: int, seed: int = 42) -> None:
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates["netherlands_temperate"]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(n, date(2024, 4, 1))
    for rec in series.records:
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )


# ---------------------------------------------------------------------------
# ManagementEvent / ManagementPlan dataclass tests
# ---------------------------------------------------------------------------
class TestManagementEvent:
    def test_create(self) -> None:
        ev = ManagementEvent(day=10, action="irrigate", params={"amount_mm": 30.0})
        assert ev.day == 10
        assert ev.action == "irrigate"
        assert ev.params["amount_mm"] == 30.0

    def test_to_dict_from_dict_roundtrip(self) -> None:
        ev = ManagementEvent(
            day=20, action="fertilize", params={"type": "urea", "amount_kg_ha": 100.0}
        )
        d = ev.to_dict()
        restored = ManagementEvent.from_dict(d)
        assert restored == ev


class TestManagementPlan:
    def test_events_for_day(self) -> None:
        plan = ManagementPlan(
            events=[
                ManagementEvent(day=5, action="irrigate", params={"amount_mm": 20.0}),
                ManagementEvent(day=10, action="irrigate", params={"amount_mm": 30.0}),
                ManagementEvent(
                    day=5,
                    action="fertilize",
                    params={"type": "urea", "amount_kg_ha": 50.0},
                ),
            ]
        )
        day5 = plan.events_for_day(5)
        assert len(day5) == 2
        assert plan.events_for_day(10) == [plan.events[1]]
        assert plan.events_for_day(99) == []

    def test_to_dict_from_dict_roundtrip(self) -> None:
        plan = ManagementPlan(
            events=[
                ManagementEvent(day=5, action="irrigate", params={"amount_mm": 20.0}),
                ManagementEvent(
                    day=20,
                    action="fertilize",
                    params={"type": "tsp", "amount_kg_ha": 30.0},
                ),
            ]
        )
        d = plan.to_dict()
        restored = ManagementPlan.from_dict(d)
        assert restored.events == plan.events

    def test_empty_plan(self) -> None:
        plan = ManagementPlan()
        assert plan.events == []
        assert plan.events_for_day(0) == []


# ---------------------------------------------------------------------------
# AC: irrigation on day 30 — moisture increases on day 30, not day 29
# ---------------------------------------------------------------------------
def test_irrigation_executes_on_scheduled_day() -> None:
    """Plan irrigation on day 5. Compare with unirrigated run to verify effect."""
    plan = ManagementPlan(
        events=[ManagementEvent(day=5, action="irrigate", params={"amount_mm": 50.0})]
    )

    # Run with plan
    orch_plan = _make_orch(plan)
    orch_plan.water_state.theta[0] = orch_plan.profile.layers[0].wilting_point
    _step_days(orch_plan, 10)
    theta_with_plan = orch_plan.water_state.theta[0]

    # Run without plan (same conditions)
    orch_no_plan = _make_orch()
    orch_no_plan.water_state.theta[0] = orch_no_plan.profile.layers[0].wilting_point
    _step_days(orch_no_plan, 10)
    theta_no_plan = orch_no_plan.water_state.theta[0]

    # Irrigated run should have more water than non-irrigated
    assert theta_with_plan > theta_no_plan


# ---------------------------------------------------------------------------
# AC: fertilizer on day 20 — NH4 increases on day 20
# ---------------------------------------------------------------------------
def test_fertilizer_executes_on_scheduled_day() -> None:
    """Plan urea on day 20. Verify NH4 increases on that day."""
    plan = ManagementPlan(
        events=[
            ManagementEvent(
                day=20,
                action="fertilize",
                params={"type": "urea", "amount_kg_ha": 100.0},
            )
        ]
    )
    orch = _make_orch(plan)

    # Run 20 days (days 0-19)
    _step_days(orch, 20)
    nh4_before = orch.n_state.nh4[0]

    # Run day 20
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    gen = SyntheticWeatherGenerator(climates.climates["netherlands_temperate"], seed=42)
    series = gen.generate(21, date(2024, 4, 1))
    rec = series.records[20]
    orch.step_day(
        drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
        tmin_c=rec.tmin_c,
        tmax_c=rec.tmax_c,
        par_mj_m2=rec.shortwave_mj_m2 or 12.0,
        sim_date=rec.day,
    )
    assert orch.n_state.nh4[0] > nh4_before


# ---------------------------------------------------------------------------
# AC: orchestrator accepts management_plan
# ---------------------------------------------------------------------------
def test_orchestrator_accepts_plan() -> None:
    plan = ManagementPlan(
        events=[ManagementEvent(day=5, action="irrigate", params={"amount_mm": 10.0})]
    )
    orch = _make_orch(plan)
    assert orch.management_plan is plan


def test_orchestrator_defaults_to_empty_plan() -> None:
    orch = _make_orch()
    assert orch.management_plan.events == []


# ---------------------------------------------------------------------------
# AC: day counter increments
# ---------------------------------------------------------------------------
def test_day_counter_increments() -> None:
    orch = _make_orch()
    assert orch._day_counter == 0
    _step_days(orch, 5)
    assert orch._day_counter == 5
