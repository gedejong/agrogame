from __future__ import annotations

from agrogame.events import EventBus
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

    def _vernalization_increment(
        self,
        tmin_c: float,
        tmax_c: float,
        vernalization_temp_range_c: tuple[float, float],
    ) -> float:
        if self.params.vernalization_required_units is None:
            return 0.0
        vmin, vmax = vernalization_temp_range_c
        tmean = (max(tmin_c, vmin) + min(tmax_c, vmax)) / 2.0
        return 1.0 if vmin <= tmean <= vmax else 0.0

    def _vernalization_met(self) -> bool:
        return (
            self.params.vernalization_required_units is None
            or self.state.vernalization_units
            >= self.params.vernalization_required_units
        )

    def development_stage(self) -> float:
        """Continuous development stage (DVS) on the WOFOST scale.

        0.0 at sowing, 1.0 at anthesis, 2.0 at physiological maturity,
        piecewise-linear in accumulated GDD between the stage thresholds
        (Van Diepen et al. 1989; Supit et al. 1994). The pre-flowering
        branch is capped just below 1.0 so a crop held back by an unmet
        vernalization or photoperiod requirement never reports anthesis,
        however much thermal time it has banked; the reproductive branch
        then runs from the flowering to the maturity threshold.
        """
        thr = self.params.thresholds
        gdd = max(self.state.accumulated_gdd, 0.0)
        pre_flowering = (
            PhenologyStage.PLANTED,
            PhenologyStage.EMERGED,
            PhenologyStage.VEGETATIVE,
        )
        if self.state.stage in pre_flowering:
            if thr.flowering_gdd <= 0.0:
                return 0.99
            return min(gdd / thr.flowering_gdd, 0.99)
        if self.state.stage == PhenologyStage.MATURITY:
            return 2.0
        span = thr.maturity_gdd - thr.flowering_gdd
        if span <= 0.0:
            return 2.0
        frac = (gdd - thr.flowering_gdd) / span
        return 1.0 + min(max(frac, 0.0), 1.0)

    def _resolve_next_stage(self) -> PhenologyStage | None:
        thr = self.params.thresholds
        gdd = self.state.accumulated_gdd
        transitions: list[tuple[PhenologyStage, float, PhenologyStage]] = [
            (PhenologyStage.PLANTED, thr.emergence_gdd, PhenologyStage.EMERGED),
            (PhenologyStage.EMERGED, thr.emergence_gdd, PhenologyStage.VEGETATIVE),
            (PhenologyStage.FLOWERING, thr.flowering_gdd, PhenologyStage.GRAIN_FILL),
            (PhenologyStage.GRAIN_FILL, thr.maturity_gdd, PhenologyStage.MATURITY),
        ]
        for from_stage, threshold, to_stage in transitions:
            if self.state.stage == from_stage and gdd >= threshold:
                return to_stage
        # Vegetative -> Flowering requires vernalization check
        if (
            self.state.stage == PhenologyStage.VEGETATIVE
            and gdd >= thr.flowering_gdd
            and self._vernalization_met()
        ):
            return PhenologyStage.FLOWERING
        return None

    def daily_step(
        self,
        tmin_c: float,
        tmax_c: float,
        photoperiod_h: float | None = None,
        vernalization_temp_range_c: tuple[float, float] = (0.0, 10.0),
    ) -> PhenologyState:
        gdd = self._daily_gdd(tmin_c, tmax_c, photoperiod_h)
        vernal_add = self._vernalization_increment(
            tmin_c, tmax_c, vernalization_temp_range_c
        )
        self.state = PhenologyState(
            accumulated_gdd=self.state.accumulated_gdd + gdd,
            stage=self.state.stage,
            vernalization_units=self.state.vernalization_units + vernal_add,
        )
        if self.event_bus is not None:
            self.event_bus.emit(
                GddAccumulated(daily_gdd=gdd, total_gdd=self.state.accumulated_gdd)
            )

        next_stage = self._resolve_next_stage()
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
