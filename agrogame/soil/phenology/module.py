from __future__ import annotations

from .params import CropPhenologyParams
from .types import PhenologyStage, PhenologyState


class PhenologyModule:
    def __init__(self, params: CropPhenologyParams):
        self.params = params
        self.state = PhenologyState(accumulated_gdd=0.0, stage=PhenologyStage.PLANTED)

    def _daily_gdd(self, tmin_c: float, tmax_c: float) -> float:
        tmin = max(tmin_c, self.params.base_temperature_c)
        tmax = min(tmax_c, self.params.max_temperature_c)
        tmean = (tmin + tmax) / 2.0
        return max(0.0, tmean - self.params.base_temperature_c)

    def update_daily(self, tmin_c: float, tmax_c: float) -> PhenologyState:
        gdd = self._daily_gdd(tmin_c, tmax_c)
        self.state.accumulated_gdd += gdd

        thr = self.params.thresholds
        if (
            self.state.stage == PhenologyStage.PLANTED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            self.state.stage = PhenologyStage.EMERGED
        elif (
            self.state.stage == PhenologyStage.EMERGED
            and self.state.accumulated_gdd >= thr.emergence_gdd
        ):
            self.state.stage = PhenologyStage.VEGETATIVE
        elif (
            self.state.stage in (PhenologyStage.VEGETATIVE,)
            and self.state.accumulated_gdd >= thr.flowering_gdd
        ):
            self.state.stage = PhenologyStage.FLOWERING
        elif (
            self.state.stage == PhenologyStage.FLOWERING
            and self.state.accumulated_gdd >= thr.flowering_gdd
        ):
            self.state.stage = PhenologyStage.GRAIN_FILL
        elif (
            self.state.stage in (PhenologyStage.GRAIN_FILL,)
            and self.state.accumulated_gdd >= thr.maturity_gdd
        ):
            self.state.stage = PhenologyStage.MATURITY

        return self.state
