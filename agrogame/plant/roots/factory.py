from __future__ import annotations

from agrogame.events import EventBus
from agrogame.params.models import CropParameters

from .module import RootModule
from .params import RootParams


class RootFactory:
    @staticmethod
    def build_from_crop_params(
        crop: CropParameters, event_bus: EventBus | None = None
    ) -> RootModule:
        rp = RootParams(
            max_depth_cm=getattr(crop, "max_root_depth_cm", 120.0),
            growth_rate_cm_per_day=getattr(crop, "root_growth_rate_cm_per_day", 1.5),
            distribution=getattr(crop, "root_distribution", "exponential"),
            turnover_rate_per_day=getattr(crop, "root_turnover_rate_per_day", 0.005),
            proliferation_strength=getattr(crop, "root_proliferation_strength", 0.0),
            stage_multipliers=getattr(crop, "root_stage_multipliers", None),
        )
        return RootModule(rp, event_bus=event_bus)
