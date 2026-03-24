from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from time import perf_counter
from typing import Dict, List, Tuple, cast

from agrogame.soil.models import SoilProfile
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.weather.types import WeatherRecord
from .orchestrator import FullSimulationOrchestrator


class ActionType(Enum):
    IRRIGATION = "irrigation"
    FERTILIZER_AN = "fertilizer_an"
    FERTILIZER_UREA = "fertilizer_urea"
    LIME = "lime"
    HARVEST = "harvest"


@dataclass
class ScheduledAction:
    day_index: int
    action: ActionType
    amount: float
    layer: int = 0


@dataclass
class SeasonResults:
    days_processed: int
    total_runtime_s: float
    finished: bool


class EventScheduler:
    def __init__(self) -> None:
        self._by_day: Dict[int, List[ScheduledAction]] = {}

    def schedule(self, action: ScheduledAction) -> None:
        self._by_day.setdefault(action.day_index, []).append(action)

    def for_day(self, day_index: int) -> List[ScheduledAction]:
        return list(self._by_day.get(day_index, ()))

    def snapshot(self) -> Dict[int, List[Tuple[str, float, int]]]:
        snap: Dict[int, List[Tuple[str, float, int]]] = {}
        for di, items in self._by_day.items():
            snap[di] = [(it.action.value, it.amount, it.layer) for it in items]
        return snap

    @classmethod
    def from_snapshot(
        cls, snap: Dict[int, List[Tuple[str, float, int]]]
    ) -> EventScheduler:
        sched = cls()
        for di, items in snap.items():
            for action, amount, layer in items:
                sched.schedule(
                    ScheduledAction(
                        day_index=int(di),
                        action=ActionType(action),
                        amount=float(amount),
                        layer=int(layer),
                    )
                )
        return sched


class SimulationEngine:
    """High-level daily loop orchestrating the season run.

    Wrapper around `FullSimulationOrchestrator` to provide:
    - Daily loop with variable step size
    - Simple management action scheduling (irrigation, fertilizer, lime)
    - Pause/resume and basic checkpoint/restore of loop state
    - Metrics collection
    """

    def __init__(
        self,
        profile: SoilProfile,
        weather_file: str | Path,
        *,
        max_days: int | None = None,
    ) -> None:
        self.profile = profile
        self.weather_file = str(weather_file)
        self.weather_records: List[WeatherRecord] = list(
            load_weather(Path(self.weather_file)).records
        )
        self.max_days = max_days or len(self.weather_records)

        self.orchestrator = FullSimulationOrchestrator(profile)
        self.scheduler = EventScheduler()

        self.current_day: int = 0
        self.is_running: bool = False
        self.days_per_step: int = 1

        self._total_runtime_s: float = 0.0

    # --- Control -----------------------------------------------------
    def set_speed(self, days_per_step: int) -> None:
        self.days_per_step = max(1, int(days_per_step))

    def pause(self) -> None:
        self.is_running = False

    def resume(self) -> None:
        self.is_running = True

    # --- Scheduling --------------------------------------------------
    def schedule_irrigation(self, day_index: int, mm: float) -> None:
        self.scheduler.schedule(
            ScheduledAction(
                day_index=day_index, action=ActionType.IRRIGATION, amount=float(mm)
            )
        )

    def schedule_fertilizer_an(
        self, day_index: int, kg_ha: float, layer: int = 0
    ) -> None:
        self.scheduler.schedule(
            ScheduledAction(
                day_index=day_index,
                action=ActionType.FERTILIZER_AN,
                amount=float(kg_ha),
                layer=int(layer),
            )
        )

    def schedule_fertilizer_urea(
        self, day_index: int, kg_ha: float, layer: int = 0
    ) -> None:
        self.scheduler.schedule(
            ScheduledAction(
                day_index=day_index,
                action=ActionType.FERTILIZER_UREA,
                amount=float(kg_ha),
                layer=int(layer),
            )
        )

    def schedule_lime(self, day_index: int, kg_ha: float, layer: int = 0) -> None:
        self.scheduler.schedule(
            ScheduledAction(
                day_index=day_index,
                action=ActionType.LIME,
                amount=float(kg_ha),
                layer=int(layer),
            )
        )

    def schedule_harvest(self, day_index: int) -> None:
        self.scheduler.schedule(
            ScheduledAction(
                day_index=day_index,
                action=ActionType.HARVEST,
                amount=0.0,
                layer=0,
            )
        )

    # --- Persistence -------------------------------------------------
    def checkpoint(self) -> dict:
        return {
            "current_day": self.current_day,
            "is_running": self.is_running,
            "days_per_step": self.days_per_step,
            "scheduler": self.scheduler.snapshot(),
        }

    def restore(self, state: dict) -> None:
        self.current_day = int(state.get("current_day", 0))
        self.is_running = bool(state.get("is_running", False))
        self.days_per_step = int(state.get("days_per_step", 1))
        snap = cast(Dict[int, List[Tuple[str, float, int]]], state.get("scheduler", {}))
        self.scheduler = EventScheduler.from_snapshot(snap)

    # --- Main loop ---------------------------------------------------
    def run_season(self) -> SeasonResults:
        self.is_running = True
        start = perf_counter()
        while self.is_running and not self._is_done():
            self.advance_day()
        self._total_runtime_s += perf_counter() - start
        return SeasonResults(
            days_processed=self.current_day,
            total_runtime_s=self._total_runtime_s,
            finished=self._is_done(),
        )

    def advance_day(self) -> None:
        if self._is_done():
            return
        # Execute scheduled management actions for this day
        for action in self.scheduler.for_day(self.current_day):
            self._apply_action(action)

        # Prepare weather and drivers for a burst of days (speed)
        step = self.days_per_step
        for _ in range(step):
            if self._is_done():
                break
            rec = self.weather_records[self.current_day]
            rain = rec.precip_mm or 0.0
            irrigation = self._irrigation_for_day(self.current_day)
            drivers = DailyDrivers(
                rainfall_mm=rain, irrigation_mm=irrigation, evaporation_mm=0.0
            )
            # Prefer net radiation when available; convert to PAR using ~0.48
            par = (rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0) * 0.48
            self.orchestrator.step_day(
                drivers=drivers,
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                par_mj_m2=par,
            )
            self.current_day += 1

    # --- Helpers -----------------------------------------------------
    def _is_done(self) -> bool:
        # Stop on maturity if available
        from agrogame.soil.phenology import PhenologyStage  # local import

        stg = getattr(getattr(self.orchestrator, "phenology", None), "state", None)
        if getattr(stg, "stage", None) is PhenologyStage.MATURITY:
            return True
        return self.current_day >= min(self.max_days, len(self.weather_records))

    def _apply_action(self, action: ScheduledAction) -> None:
        if action.action is ActionType.IRRIGATION:
            # Irrigation is added to drivers for the day via _irrigation_for_day
            return
        if action.action is ActionType.FERTILIZER_AN:
            self.orchestrator.n_cycle.apply_ammonium_nitrate(
                action.layer, action.amount
            )
            return
        if action.action is ActionType.FERTILIZER_UREA:
            self.orchestrator.n_cycle.apply_urea(action.layer, action.amount)
            return
        if action.action is ActionType.LIME:
            # Emit chemistry event directly via event bus
            from agrogame.soil.chemistry.events import LimeApplied  # local import

            self.orchestrator.event_bus.emit(
                LimeApplied(layer=int(action.layer), rate_kg_ha=float(action.amount))
            )
            return
        if action.action is ActionType.HARVEST:
            # Emit a harvest event to cause canopy LAI (and biomass) drop
            from agrogame.soil.canopy.events import Harvested  # local import

            self.orchestrator.event_bus.emit(Harvested(fraction_remaining=0.1))
            # Do not force-stop; allow post-harvest days to be simulated

    def _irrigation_for_day(self, day_index: int) -> float:
        total = 0.0
        for sa in self.scheduler.for_day(day_index):
            if sa.action is ActionType.IRRIGATION:
                total += sa.amount
        return total
