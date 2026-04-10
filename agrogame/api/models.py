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

    # Redox state (AGRO-73)
    redox_eh: list[float] = Field(
        default_factory=list, description="Redox potential per layer (mV)"
    )
    dominant_acceptor: list[str] = Field(
        default_factory=list,
        description="Dominant electron acceptor per layer (O2, NO3, Fe3+, CH4)",
    )

    # Micronutrients (#214)
    fe_available: list[float] = Field(
        default_factory=list, description="Plant-available Fe per layer (ppm)"
    )
    zn_available: list[float] = Field(
        default_factory=list, description="Plant-available Zn per layer (ppm)"
    )
    mn_available: list[float] = Field(
        default_factory=list, description="Plant-available Mn per layer (ppm)"
    )

    # Aggregation (#248)
    agg_macro: list[float] = Field(
        default_factory=list, description="Macroaggregate fraction per layer"
    )
    agg_meso: list[float] = Field(
        default_factory=list, description="Mesoaggregate fraction per layer"
    )
    agg_micro: list[float] = Field(
        default_factory=list, description="Microaggregate fraction per layer"
    )
    agg_mwd: list[float] = Field(
        default_factory=list, description="Mean weight diameter per layer (mm)"
    )

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
    start_date: str = Field(description="Simulation start date (ISO format)")
    end_date: str = Field(description="Simulation end date (ISO format)")
    season_number: int = Field(description="1-based season counter")
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


# ---------------------------------------------------------------------------
# Day-by-day game loop (#125)
# ---------------------------------------------------------------------------


class DayWeatherResponse(BaseModel):
    date: str = Field(description="ISO date")
    tmin_c: float = Field(description="Minimum temperature (°C)")
    tmax_c: float = Field(description="Maximum temperature (°C)")
    rain_mm: float = Field(description="Precipitation (mm)")


class PatchDayResponse(BaseModel):
    patch_idx: int
    crop_key: str
    crop_stage: str = Field(description="Phenology stage name")
    grain_g_m2: float
    root_depth_cm: float = Field(description="Current root penetration depth (cm)")
    lai: float = Field(description="Leaf area index (m²/m²)")
    soil_theta_surface: float = Field(description="Top-layer volumetric water content")
    som_total_c_g_m2: float = Field(description="Total SOM carbon (g/m²)")
    water_stress: float = Field(
        description="Plant water stress: transpiration supply/demand"
        " (0=severe, 1=none)"
    )
    soil_state: SoilStateResponse | None = Field(
        default=None, description="Full per-layer soil state for 3D view"
    )
    events: list[dict] = Field(
        default_factory=list,
        description="Simulation events emitted during this day step"
        " (see docs/api-events.md for schema)",
    )


class DailySnapshot(BaseModel):
    """Lightweight per-day per-patch snapshot for sparkline history."""

    day_number: int
    date: str
    field_id: str
    patch_idx: int
    crop_stage: str = ""
    lai: float = 0.0
    grain_g_m2: float = 0.0
    water_stress: float = 1.0
    soil_theta_surface: float = 0.0
    n_available_total: float = 0.0
    redox_eh_surface: float = 400.0
    fe_available_surface: float = 10.0
    zn_available_surface: float = 1.2
    mn_available_surface: float = 18.0
    agg_mwd_surface: float = 0.55
    rain_mm: float = 0.0
    events: list[dict] = Field(
        default_factory=list,
        description="Simulation events emitted during this day",
    )


class DayResultResponse(BaseModel):
    day_number: int
    date: str = Field(description="Current date (ISO format)")
    weather: DayWeatherResponse
    patches: dict[str, list[PatchDayResponse]]
    season_complete: bool = Field(
        default=False, description="True when crop mature or max days"
    )
    balance_credits: int
    daily_snapshots: list[DailySnapshot] = Field(
        default_factory=list,
        description="Per-day snapshots for all stepped days" " (populated when days>1)",
    )


class ActionRequest(BaseModel):
    field_id: str = "field_1"
    action: str = Field(description="irrigate, fertilize, plant, harvest")
    params: dict = Field(default_factory=dict)


class ActionResponse(BaseModel):
    status: str
    action: str
    cost_credits: int
    balance_credits: int
    day_number: int


class ForecastDayResponse(BaseModel):
    date: str
    tmin_c: float
    tmax_c: float
    rain_mm: float


class ForecastResponse(BaseModel):
    current_day: int
    forecast: list[ForecastDayResponse]


# ---------------------------------------------------------------------------
# Harvest report (#116)
# ---------------------------------------------------------------------------


class PatchYieldReport(BaseModel):
    patch_idx: int
    crop_key: str
    soil_profile: str
    grain_t_ha: float = Field(description="Grain yield (t/ha)")
    gyga_potential_t_ha: float = Field(
        description="GYGA water-limited potential (t/ha)"
    )
    yield_ratio: float = Field(description="Simulated / GYGA potential (0-1)")
    grade: str = Field(description="Letter grade A-F based on yield ratio")
    som_total_c_g_m2: float
    theta_surface: float


class CostBreakdown(BaseModel):
    category: str
    description: str
    amount_credits: int


class HarvestReportResponse(BaseModel):
    season_number: int
    start_date: str
    end_date: str
    total_days: int
    patches: dict[str, list[PatchYieldReport]]
    revenue_credits: int
    costs: list[CostBreakdown]
    total_cost_credits: int
    profit_credits: int
    balance_before: int
    balance_after: int
    balance_delta: int
