from __future__ import annotations

from agrogame.soil.water.event_bus import EventBus
from .params import CropPhenologyParams
from .types import PhenologyStage, PhenologyState
from .events import GddAccumulated, StageChanged


class PhenologyModule:
    """Thermal-time phenology with optional photoperiod and vernalization.

    - Accumulates GDD using base and max temperature caps
    - Optional photoperiod sensitivity (linear around 12h)
    - Optional vernalization gating before flowering (units/day in cool range)
    - Emits GddAccumulated and StageChanged events via EventBus
    """

    def __init__(self, params: CropPhenologyParams, event_bus: EventBus | None = None):
        self.params = params
        self.state: PhenologyState = PhenologyState(
            accumulated_gdd=0.0, stage=PhenologyStage.PLANTED, vernalization_units=0.0
        )
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
        self,
        tmin_c: float,
        tmax_c: float,
        photoperiod_h: float | None = None,
        vernalization_temp_range_c: tuple[float, float] = (0.0, 10.0),
    ) -> PhenologyState:
        gdd = self._daily_gdd(tmin_c, tmax_c, photoperiod_h)
        vernal_add = 0.0
        if self.params.vernalization_required_units is not None:
            vmin, vmax = vernalization_temp_range_c
            # Simple model: add 1 unit/day if mean temp within [vmin, vmax]
            tmean = (max(tmin_c, vmin) + min(tmax_c, vmax)) / 2.0
            if vmin <= tmean <= vmax:
                vernal_add = 1.0
        self.state = PhenologyState(
            accumulated_gdd=self.state.accumulated_gdd + gdd,
            stage=self.state.stage,
            vernalization_units=self.state.vernalization_units + vernal_add,
        )
        if self.event_bus is not None:
            self.event_bus.emit(
                GddAccumulated(daily_gdd=gdd, total_gdd=self.state.accumulated_gdd)
            )

        thr = self.params.thresholds
        next_stage: PhenologyStage | None = None
        if (
            self.state.stage == PhenologyStage.PLANTED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            next_stage = PhenologyStage.EMERGED
        elif (
            self.state.stage == PhenologyStage.EMERGED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            next_stage = PhenologyStage.VEGETATIVE
        elif (
            self.state.stage in (PhenologyStage.VEGETATIVE,)
            and self.state.accumulated_gdd >= thr.flowering_gdd
            and (
                self.params.vernalization_required_units is None
                or self.state.vernalization_units
                >= self.params.vernalization_required_units
            )
        ):
            next_stage = PhenologyStage.FLOWERING
        elif (
            self.state.stage == PhenologyStage.FLOWERING
            and self.state.accumulated_gdd >= thr.flowering_gdd
        ):
            next_stage = PhenologyStage.GRAIN_FILL
        elif (
            self.state.stage in (PhenologyStage.GRAIN_FILL,)
            and self.state.accumulated_gdd >= thr.maturity_gdd
        ):
            next_stage = PhenologyStage.MATURITY

        if next_stage is not None:
            prev = self.state.stage
            self.state = PhenologyState(
                accumulated_gdd=self.state.accumulated_gdd,
                stage=next_stage,
                vernalization_units=self.state.vernalization_units,
            )
            if self.event_bus is not None:
                self.event_bus.emit(
                    StageChanged(
                        from_stage=prev,
                        to_stage=self.state.stage,
                        at_gdd=self.state.accumulated_gdd,
                    )
                )

        return self.state
