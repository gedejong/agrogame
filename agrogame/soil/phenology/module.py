from __future__ import annotations

from agrogame.soil.water.event_bus import EventBus
from .params import CropPhenologyParams
from .types import PhenologyStage, PhenologyState
from .events import GddAccumulated, StageChanged


class PhenologyModule:
    def __init__(self, params: CropPhenologyParams, event_bus: EventBus | None = None):
        self.params = params
        self.state = PhenologyState(accumulated_gdd=0.0, stage=PhenologyStage.PLANTED)
        self.event_bus = event_bus

    def _daily_gdd(
        self, tmin_c: float, tmax_c: float, photoperiod_h: float | None
    ) -> float:
        tmin = max(tmin_c, self.params.base_temperature_c)
        tmax = min(tmax_c, self.params.max_temperature_c)
        tmean = (tmin + tmax) / 2.0
        gdd = max(0.0, tmean - self.params.base_temperature_c)
        if (
            photoperiod_h is not None
            and self.params.photoperiod_sensitivity is not None
        ):
            # Simple linear adjustment around 12h daylength
            adj = 1.0 + self.params.photoperiod_sensitivity * (
                (photoperiod_h - 12.0) / 12.0
            )
            gdd *= max(0.0, adj)
        return gdd

    def update_daily(
        self, tmin_c: float, tmax_c: float, photoperiod_h: float | None = None
    ) -> PhenologyState:
        gdd = self._daily_gdd(tmin_c, tmax_c, photoperiod_h)
        self.state.accumulated_gdd += gdd
        if self.event_bus is not None:
            self.event_bus.emit(
                GddAccumulated(daily_gdd=gdd, total_gdd=self.state.accumulated_gdd)
            )

        thr = self.params.thresholds
        if (
            self.state.stage == PhenologyStage.PLANTED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            prev = self.state.stage
            self.state.stage = PhenologyStage.EMERGED
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )
        elif (
            self.state.stage == PhenologyStage.EMERGED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            prev = self.state.stage
            self.state.stage = PhenologyStage.VEGETATIVE
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )
        elif (
            self.state.stage in (PhenologyStage.VEGETATIVE,)
            and self.state.accumulated_gdd >= thr.flowering_gdd
        ):
            prev = self.state.stage
            self.state.stage = PhenologyStage.FLOWERING
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )
        elif (
            self.state.stage == PhenologyStage.FLOWERING
            and self.state.accumulated_gdd >= thr.flowering_gdd
        ):
            prev = self.state.stage
            self.state.stage = PhenologyStage.GRAIN_FILL
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )
        elif (
            self.state.stage in (PhenologyStage.GRAIN_FILL,)
            and self.state.accumulated_gdd >= thr.maturity_gdd
        ):
            prev = self.state.stage
            self.state.stage = PhenologyStage.MATURITY
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )

        return self.state
