"""Pydantic request/response models for the game API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PatchConfigRequest(BaseModel):
    soil_profile_key: str = "loam_temperate"
    crop_key: str = "maize"
    climate_key: str = "netherlands_temperate"
    area_fraction: float = 1.0


class FieldConfigRequest(BaseModel):
    field_id: str
    patches: list[PatchConfigRequest]


class CreateGameRequest(BaseModel):
    fields: list[FieldConfigRequest]
    starting_credits: int = 10000


class ManagementEventRequest(BaseModel):
    day: int
    action: str
    params: dict = Field(default_factory=dict)


class PlanRequest(BaseModel):
    field_id: str
    events: list[ManagementEventRequest]


class ReviseRequest(BaseModel):
    field_id: str
    from_day: int
    events: list[ManagementEventRequest]


class SoilStateResponse(BaseModel):
    """Per-patch soil state snapshot after season execution."""

    # Per-layer arrays (one value per soil layer, typically 5 layers)
    water_theta: list[float] = Field(description="Volumetric water content per layer")
    n_no3: list[float] = Field(description="Nitrate-N per layer (g/m²)")
    n_nh4: list[float] = Field(description="Ammonium-N per layer (g/m²)")
    n_organic: list[float] = Field(description="Organic N per layer (g/m²)")
    p_available: list[float] = Field(description="Available P per layer (g/m²)")
    ph: list[float] = Field(description="Soil pH per layer")

    # SOM pool summaries (per-layer C in g/m²)
    som_labile_c: list[float] = Field(description="Labile SOM carbon per layer")
    som_intermediate_c: list[float] = Field(
        description="Intermediate SOM carbon per layer"
    )
    som_stable_c: list[float] = Field(description="Stable SOM carbon per layer")

    # Microbial state
    microbe_c: list[float] = Field(description="Microbial biomass C per layer")

    # Aggregates
    som_total_c_g_m2: float = Field(description="Total SOM carbon across all layers")
    theta_surface: float = Field(description="Top-layer water content (theta[0])")


class PatchResultResponse(BaseModel):
    patch_idx: int
    crop_key: str
    grain_g_m2: float
    grain_kg_ha: float
    soil_state: SoilStateResponse | None = Field(
        default=None, description="Post-season soil state snapshot"
    )


class SeasonResultResponse(BaseModel):
    total_days: int
    pause_count: int
    field_results: dict[str, list[PatchResultResponse]]


class PauseEventResponse(BaseModel):
    day: int
    reason: str
    message: str


class GameStatusResponse(BaseModel):
    game_id: str
    phase: str
    current_day: int
    balance_credits: int
    pause_events: list[PauseEventResponse] = Field(default_factory=list)
    season_result: SeasonResultResponse | None = None


class GameCreatedResponse(BaseModel):
    game_id: str
    phase: str
    balance_credits: int
    field_count: int
