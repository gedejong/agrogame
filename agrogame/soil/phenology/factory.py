from __future__ import annotations

from agrogame.params.models import CropParameters
from agrogame.events import EventBus

from .module import PhenologyModule
from .params import CropPhenologyParams, GrowthStageThresholds


def build_from_crop_params(
    crop: CropParameters, event_bus: EventBus | None = None
) -> PhenologyModule:
    tt = crop.thermal_time
    max_temp = getattr(tt, "max_temp_c", None)
    photoperiod = getattr(tt, "photoperiod_sensitivity", None)
    vernal = getattr(tt, "vernalization_required_units", None)
    params = CropPhenologyParams(
        base_temperature_c=tt.base_temp_c,
        max_temperature_c=max_temp if max_temp is not None else 45.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=tt.emergence_dd,
            flowering_gdd=tt.flowering_dd,
            maturity_gdd=tt.maturity_dd,
        ),
        photoperiod_sensitivity=photoperiod,
        vernalization_required_units=vernal,
    )
    return PhenologyModule(params=params, event_bus=event_bus)
