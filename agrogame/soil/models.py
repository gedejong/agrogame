from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field, PositiveFloat, model_validator


SoilTexture = Literal[
    "sand",
    "sandy_loam",
    "loam",
    "clay_loam",
    "clay",
    "peat",
]


class SoilLayer(BaseModel):
    depth_cm: PositiveFloat = Field(..., description="Layer thickness in cm")
    texture: SoilTexture = Field(
        ..., description="USDA-like texture class for the layer"
    )
    field_capacity: float = Field(
        ..., description="Volumetric water content at field capacity (m3/m3)"
    )
    wilting_point: float = Field(
        ..., description="Volumetric water content at wilting point (m3/m3)"
    )
    saturation: float = Field(
        ..., description="Volumetric water content at saturation (m3/m3)"
    )
    bulk_density_g_cm3: PositiveFloat = Field(..., description="Bulk density (g/cm3)")
    ksat_mm_per_hour: PositiveFloat = Field(
        ..., description="Saturated hydraulic conductivity (mm/hour)"
    )
    organic_matter_pct: float = Field(..., description="Organic matter percentage (%)")
    initial_no3_kg_ha: float = Field(
        ..., description="Initial nitrate in topsoil layer (kg/ha)"
    )
    initial_nh4_kg_ha: float = Field(
        ..., description="Initial ammonium in topsoil layer (kg/ha)"
    )
    initial_p_kg_ha: float = Field(
        ..., description="Initial phosphorus in topsoil layer (kg/ha)"
    )

    @model_validator(mode="after")
    def validate_water_bounds(self) -> "SoilLayer":
        if not (
            0.0 <= self.wilting_point < self.field_capacity < self.saturation <= 0.8
        ):
            raise ValueError(
                "Expected 0 <= wilting_point < field_capacity < saturation <= 0.8"
            )
        if self.organic_matter_pct < 0.0:
            raise ValueError("organic_matter_pct must be >= 0")
        return self


class SoilProfile(BaseModel):
    name: str = Field(..., description="Human-readable soil profile name")
    layers: List[SoilLayer] = Field(
        ..., min_length=3, description="Soil layers from surface to depth"
    )

    @model_validator(mode="after")
    def validate_depth(self) -> "SoilProfile":
        total_depth = sum(layer.depth_cm for layer in self.layers)
        if total_depth < 100.0:
            raise ValueError(
                f"Total profile depth must be at least 100 cm (got {total_depth})"
            )
        return self


class SoilLibrary(BaseModel):
    soils: Dict[str, SoilProfile] = Field(
        ..., description="Dictionary of soil profiles keyed by profile id"
    )
