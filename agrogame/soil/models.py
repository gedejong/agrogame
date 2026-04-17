from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, PositiveFloat, model_validator


SoilTexture = Literal[
    "sand",
    "sandy_loam",
    "loam",
    "clay_loam",
    "clay",
    "peat",
]

TEXTURE_TO_CLAY: Dict[str, float] = {
    "sand": 5.0,
    "sandy_loam": 12.0,
    "loam": 22.0,
    "clay_loam": 33.0,
    "clay": 50.0,
    "peat": 15.0,
}

# Sand and silt percentages by texture class.
# Ref: Rawls et al. 1982, Trans. ASAE, Table 2.
# Currently used by tests only; future PTFs will consume these.
TEXTURE_TO_SAND: Dict[str, float] = {
    "sand": 92.0,
    "sandy_loam": 65.0,
    "loam": 42.0,
    "clay_loam": 32.0,
    "clay": 22.0,
    "peat": 35.0,
}

TEXTURE_TO_SILT: Dict[str, float] = {
    "sand": 3.0,
    "sandy_loam": 23.0,
    "loam": 36.0,
    "clay_loam": 34.0,
    "clay": 28.0,
    "peat": 50.0,
}


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
    clay_pct: Optional[float] = Field(
        default=None,
        description="Clay content percentage (%). Derived from texture if not set.",
    )
    # Micronutrient initial pools (ppm DTPA-extractable). Ref: Sims & Johnson 1991.
    initial_fe_ppm: float = Field(default=10.0, description="DTPA-Fe (ppm)")
    initial_zn_ppm: float = Field(default=1.2, description="DTPA-Zn (ppm)")
    initial_mn_ppm: float = Field(default=18.0, description="DTPA-Mn (ppm)")

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
        if self.clay_pct is None:
            self.clay_pct = TEXTURE_TO_CLAY.get(self.texture, 22.0)
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
