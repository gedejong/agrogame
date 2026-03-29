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


class PatchResultResponse(BaseModel):
    patch_idx: int
    crop_key: str
    grain_g_m2: float
    grain_kg_ha: float


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
