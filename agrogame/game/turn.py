"""Game turn manager with season phases and pause events (ADR-004).

The simulation engine does not know about seasons, pauses, or planning.
This module reads daily state from the orchestrator and decides whether
to pause execution for player intervention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Generator

from agrogame.events import BaseEvent
from agrogame.sim.management import ManagementEvent, ManagementPlan

if TYPE_CHECKING:
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.types import WeatherRecord


class SeasonPhase(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    SETTLING = "settling"


class PauseReason(Enum):
    FROST_WARNING = "frost_warning"
    DROUGHT = "drought"
    NUTRIENT_DEFICIENCY = "nutrient_deficiency"


@dataclass(frozen=True)
class PauseEvent(BaseEvent):
    """Emitted when the turn manager pauses execution."""

    day: int
    reason: PauseReason
    message: str


@dataclass(frozen=True)
class PauseConfig:
    """Configurable thresholds for pause triggers."""

    frost_temp_c: float = 2.0  # pause if tmin < this
    drought_stress_threshold: float = 0.3
    drought_consecutive_days: int = 5
    n_deficiency_threshold: float = 0.5


@dataclass(frozen=True)
class SeasonResult:
    """Returned at end of season."""

    total_days: int
    grain_g_m2: float
    grain_kg_ha: float
    pause_count: int
    crop_key: str = ""


class GameTurnManager:
    """Season-based turn manager wrapping the simulation (ADR-004).

    Usage:
        mgr = GameTurnManager(orch, weather_records, plan)
        for pause in mgr.run_season():
            # player sees pause, revises plan
            mgr.revise_plan(pause.day + 1, new_events)
        result = mgr.result  # SeasonResult
    """

    def __init__(
        self,
        orch: FullSimulationOrchestrator,
        weather: list[WeatherRecord],
        plan: ManagementPlan | None = None,
        pause_config: PauseConfig | None = None,
        crop_key: str = "",
    ) -> None:
        self.orch = orch
        self.weather = weather
        self.plan = plan or ManagementPlan()
        self.orch.management_plan = self.plan
        self.pause_config = pause_config or PauseConfig()
        self.crop_key = crop_key

        self.phase = SeasonPhase.PLANNING
        self.current_day: int = 0
        self.pause_count: int = 0
        self.result: SeasonResult | None = None
        self._drought_days: int = 0
        self._last_n_stress: float = 1.0
        # Subscribe to nutrient stress events for N deficiency detection
        from agrogame.plant.events import NutrientStressComputed

        self.orch.event_bus.subscribe(NutrientStressComputed, self._on_nutrient_stress)

    def _on_nutrient_stress(self, ev: Any) -> None:
        if getattr(ev, "nutrient", "").upper() == "N":
            self._last_n_stress = max(0.0, min(1.0, float(ev.stress)))

    def run_season(self) -> Generator[PauseEvent, None, None]:
        """Execute the season, yielding PauseEvents when triggered.

        The caller iterates this generator. Each yield pauses execution.
        After handling the pause (e.g., revising the plan), the caller
        resumes by continuing iteration. When the generator exhausts,
        the season is complete and self.result is set.
        """
        self.phase = SeasonPhase.EXECUTING

        for i, rec in enumerate(self.weather):
            if i < self.current_day:
                continue

            self.orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                par_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
            self.current_day = i + 1

            pause = self._check_pause(i, rec)
            if pause is not None:
                self.phase = SeasonPhase.PAUSED
                self.pause_count += 1
                yield pause
                self.phase = SeasonPhase.EXECUTING

        self._settle()

    def _check_pause(self, day: int, rec: WeatherRecord) -> PauseEvent | None:
        cfg = self.pause_config

        # Frost warning
        if rec.tmin_c < cfg.frost_temp_c:
            return PauseEvent(
                day=day,
                reason=PauseReason.FROST_WARNING,
                message=f"Frost warning: tmin={rec.tmin_c:.1f}C",
            )

        # Drought (consecutive low water stress approximated by low theta)
        top_theta = self.orch.water_state.theta[0]
        fc = self.orch.profile.layers[0].field_capacity
        water_stress = top_theta / fc if fc > 0 else 1.0
        if water_stress < cfg.drought_stress_threshold:
            self._drought_days += 1
        else:
            self._drought_days = 0
        if self._drought_days >= cfg.drought_consecutive_days:
            self._drought_days = 0
            return PauseEvent(
                day=day,
                reason=PauseReason.DROUGHT,
                message=f"Drought: water stress {water_stress:.2f} "
                f"for {cfg.drought_consecutive_days}+ days",
            )

        # N deficiency
        if self._last_n_stress < cfg.n_deficiency_threshold:
            return PauseEvent(
                day=day,
                reason=PauseReason.NUTRIENT_DEFICIENCY,
                message=f"N deficiency: stress={self._last_n_stress:.2f}",
            )

        return None

    def _settle(self) -> None:
        self.phase = SeasonPhase.SETTLING
        grain = self.orch.canopy.state.grain_biomass_g_m2
        self.result = SeasonResult(
            total_days=self.current_day,
            grain_g_m2=grain,
            grain_kg_ha=grain * 10.0,
            pause_count=self.pause_count,
            crop_key=self.crop_key,
        )

    def revise_plan(self, from_day: int, new_events: list[ManagementEvent]) -> None:
        """Revise the management plan from a given day onward."""
        self.plan.revise(from_day, new_events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_day": self.current_day,
            "phase": self.phase.value,
            "pause_count": self.pause_count,
            "crop_key": self.crop_key,
            "plan": self.plan.to_dict(),
            "drought_days": self._drought_days,
        }

    @classmethod
    def restore_state(
        cls,
        data: dict[str, Any],
        orch: FullSimulationOrchestrator,
        weather: list[WeatherRecord],
    ) -> GameTurnManager:
        """Restore a mid-season GameTurnManager from saved state."""
        plan = ManagementPlan.from_dict(data.get("plan", {"events": []}))
        mgr = cls(
            orch=orch,
            weather=weather,
            plan=plan,
            crop_key=data.get("crop_key", ""),
        )
        mgr.current_day = int(data["current_day"])
        mgr.phase = SeasonPhase(data["phase"])
        mgr.pause_count = int(data.get("pause_count", 0))
        mgr._drought_days = int(data.get("drought_days", 0))
        return mgr
