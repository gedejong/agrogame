from __future__ import annotations

from typing import Dict, List
from pydantic import BaseModel, Field, PositiveFloat, conlist, model_validator


class ThermalTime(BaseModel):
    base_temp_c: float = Field(..., description="Base temperature in °C")
    emergence_dd: PositiveFloat
    flowering_dd: PositiveFloat
    maturity_dd: PositiveFloat


class Roots(BaseModel):
    max_depth_cm: PositiveFloat
    growth_rate_cm_per_day: PositiveFloat
    distribution: conlist(float, min_length=3)  # fraction per layer must sum ~1.0

    @model_validator(mode="after")
    def validate_distribution(self) -> "Roots":
        if not self.distribution:
            raise ValueError("distribution must contain at least 3 elements")
        total = sum(self.distribution)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"distribution must sum to 1.0 (got {total})")
        return self


class Biomass(BaseModel):
    rue_g_per_mj: PositiveFloat
    harvest_index: PositiveFloat
    partition_vegetative: Dict[str, float]
    partition_reproductive: Dict[str, float]


class CropParameters(BaseModel):
    name: str
    thermal_time: ThermalTime
    roots: Roots
    biomass: Biomass


class CropParameterLibrary(BaseModel):
    crops: Dict[str, CropParameters]
