from __future__ import annotations

from agrogame.params.models import CropParameters
from agrogame.soil.water.event_bus import EventBus

from .module import CanopyModule
from .params import CanopyParams


def build_from_crop_params(
    crop: CropParameters, event_bus: EventBus | None = None
) -> CanopyModule:
    # Fallbacks if fields are not yet defined in CropParameters
    k = getattr(crop, "extinction_coefficient", 0.6)
    rue = getattr(crop, "radiation_use_efficiency", crop.biomass.rue_g_per_mj)
    sla = getattr(crop, "specific_leaf_area", 0.02)
    lai_max = getattr(crop, "max_lai", 6.0)
    sen_rate = getattr(crop, "senescence_rate_per_day", 0.01)
    params = CanopyParams(
        extinction_coefficient_k=k,
        radiation_use_efficiency_g_per_mj=rue,
        specific_leaf_area_m2_per_g=sla,
        lai_max=lai_max,
        senescence_rate_per_day=sen_rate,
    )
    return CanopyModule(params=params, event_bus=event_bus)
