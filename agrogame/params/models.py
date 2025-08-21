from __future__ import annotations

from typing import Dict
from pydantic import BaseModel, Field, PositiveFloat, model_validator


class ThermalTime(BaseModel):
    base_temp_c: float = Field(..., description="Base temperature threshold in °C")
    emergence_dd: PositiveFloat = Field(
        ..., description="Thermal time from sowing to emergence (degree-days)"
    )
    flowering_dd: PositiveFloat = Field(
        ..., description="Thermal time from emergence to flowering (degree-days)"
    )
    maturity_dd: PositiveFloat = Field(
        ...,
        description="Thermal time from flowering to physiological maturity (degree-days)",
    )


class Roots(BaseModel):
    max_depth_cm: PositiveFloat = Field(..., description="Maximum rooting depth (cm)")
    growth_rate_cm_per_day: PositiveFloat = Field(
        ..., description="Rooting depth growth rate (cm/day)"
    )
    distribution: list[float] = Field(
        ...,
        min_length=3,
        description="Fractional root distribution per soil layer (sums to 1.0)",
    )

    @model_validator(mode="after")
    def validate_distribution(self) -> "Roots":
        if not self.distribution:
            raise ValueError("distribution must contain at least 3 elements")
        total = sum(self.distribution)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"distribution must sum to 1.0 (got {total})")
        return self


class Biomass(BaseModel):
    rue_g_per_mj: PositiveFloat = Field(
        ..., description="Radiation Use Efficiency (g biomass per MJ intercepted PAR)"
    )
    harvest_index: PositiveFloat = Field(
        ...,
        description="Harvest index: fraction of total biomass in harvestable product (0-1]",
    )
    partition_vegetative: Dict[str, float] = Field(
        ...,
        description="Biomass partition fractions during vegetative phase (sum to 1.0)",
    )
    partition_reproductive: Dict[str, float] = Field(
        ...,
        description="Biomass partition fractions during reproductive phase (sum to 1.0)",
    )

    @model_validator(mode="after")
    def validate_partitions(self) -> "Biomass":
        # Ensure harvest index is (0, 1]
        if not (0.0 < self.harvest_index <= 1.0):
            raise ValueError("harvest_index must be in (0, 1]")

        def _sum_to_one(d: Dict[str, float], name: str) -> None:
            total = sum(d.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(f"{name} must sum to 1.0 (got {total})")
            if any(v < 0.0 for v in d.values()):
                raise ValueError(f"{name} must not contain negative fractions")

        _sum_to_one(self.partition_vegetative, "partition_vegetative")
        _sum_to_one(self.partition_reproductive, "partition_reproductive")
        return self


class CropParameters(BaseModel):
    name: str = Field(..., description="Crop identifier or human-readable name")
    thermal_time: ThermalTime = Field(..., description="Thermal time requirements")
    roots: Roots = Field(..., description="Root system parameters")
    biomass: Biomass = Field(..., description="Biomass conversion and partitioning")


class CropParameterLibrary(BaseModel):
    crops: Dict[str, CropParameters] = Field(
        ..., description="Mapping from crop key to its parameter set"
    )
