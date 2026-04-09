"""FastAPI routes for the game API (ADR-005, AGRO-111)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agrogame.api.models import (
    ActionRequest,
    ActionResponse,
    CostBreakdown,
    CreateGameRequest,
    DayResultResponse,
    DayWeatherResponse,
    ForecastDayResponse,
    ForecastResponse,
    GameCreatedResponse,
    GameStatusResponse,
    HarvestReportResponse,
    PatchDayResponse,
    PatchResultResponse,
    PatchYieldReport,
    PauseEventResponse,
    PlanRequest,
    ReviseRequest,
    SeasonResultResponse,
    SoilStateResponse,
)
from agrogame.api.state import GameSession, games
from agrogame.game.economy import EconomicLedger, PriceTable
from agrogame.game.field import FieldManager, Patch, PatchConfig
from agrogame.game.turn import GameTurnManager, PauseConfig, SeasonPhase
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

from agrogame.plant.presets import load_crop_presets

router = APIRouter(prefix="/api/v1")


def _reset_all_crops(s: GameSession) -> None:
    """Reset crops on all patches, preserving soil state for next run."""
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    for field in s.field_manager.fields.values():
        for patch in field.patches:
            preset = crops.get_preset(patch.config.crop_key, patch.config.climate_key)
            patch.orch.reset_crop(preset)


def _build_soil_state(patch: "Patch") -> SoilStateResponse:
    """Build SoilStateResponse from a patch's current soil snapshot."""
    snap = patch.orch.snapshot_soil()
    som_total = (
        sum(snap.som_labile_c) + sum(snap.som_intermediate_c) + sum(snap.som_stable_c)
    )
    return SoilStateResponse(
        water_theta=list(snap.water_theta),
        n_no3=list(snap.n_no3),
        n_nh4=list(snap.n_nh4),
        n_organic=list(snap.n_organic),
        p_available=list(snap.p_available),
        ph=list(snap.ph),
        som_labile_c=list(snap.som_labile_c),
        som_intermediate_c=list(snap.som_intermediate_c),
        som_stable_c=list(snap.som_stable_c),
        microbe_c=list(snap.microbe_c),
        som_total_c_g_m2=round(som_total, 2),
        theta_surface=round(snap.water_theta[0], 4) if snap.water_theta else 0.0,
    )


def _serialize_events(patch: "Patch") -> list[dict]:
    """Serialize recorded events for a patch into JSON-safe dicts."""
    out: list[dict] = []
    for e in patch.recorder.events:
        try:
            safe = json.loads(json.dumps(e.data, default=str))
        except (TypeError, ValueError):
            safe = {"_raw": str(e.data)}
        out.append({"event_type": e.event_type, "module": e.module_name, "data": safe})
    return out


def _get_session(game_id: str) -> GameSession:
    if game_id not in games:
        raise HTTPException(status_code=404, detail=f"Game {game_id} not found")
    return games[game_id]


@router.post("/games", response_model=GameCreatedResponse)
def create_game(req: CreateGameRequest) -> GameCreatedResponse:
    """Create a new game session."""
    game_id = str(uuid.uuid4())[:8]
    fm = FieldManager()
    for fc in req.fields:
        patches = [
            PatchConfig(
                soil_profile_key=p.soil_profile_key,
                crop_key=p.crop_key,
                climate_key=p.climate_key,
                area_fraction=p.area_fraction,
            )
            for p in fc.patches
        ]
        fm.add_field(fc.field_id, patches)

    ledger = EconomicLedger(balance_credits=req.starting_credits)
    session = GameSession(game_id=game_id, field_manager=fm, ledger=ledger)
    games[game_id] = session
    return GameCreatedResponse(
        game_id=game_id,
        phase="planning",
        balance_credits=ledger.balance_credits,
        field_count=len(fm.fields),
    )


@router.get("/games/{game_id}", response_model=GameStatusResponse)
def get_game(game_id: str) -> GameStatusResponse:
    """Get current game state."""
    s = _get_session(game_id)
    phase = "planning"
    current_day = 0
    if s.turn_manager:
        phase = s.turn_manager.phase.value
        current_day = s.turn_manager.current_day
    return GameStatusResponse(
        game_id=game_id,
        phase=phase,
        current_day=current_day,
        balance_credits=s.ledger.balance_credits,
        pause_events=[
            PauseEventResponse(day=pe.day, reason=pe.reason.value, message=pe.message)
            for pe in s.pause_events
        ],
    )


@router.post("/games/{game_id}/plan")
def submit_plan(game_id: str, req: PlanRequest) -> dict:
    """Submit a management plan for a field."""
    s = _get_session(game_id)
    if req.field_id not in s.field_manager.fields:
        raise HTTPException(404, f"Field {req.field_id} not found")
    plan = ManagementPlan(
        events=[
            ManagementEvent(day=e.day, action=e.action, params=e.params)
            for e in req.events
        ]
    )
    field = s.field_manager.fields[req.field_id]
    for patch in field.patches:
        patch.orch.management_plan = plan
    return {"status": "plan_accepted", "event_count": len(plan.events)}


@router.post("/games/{game_id}/start-season", response_model=SeasonResultResponse)
def start_season(game_id: str, days: int = 150, seed: int = 42) -> SeasonResultResponse:
    """Run N simulation days, continuing from the session's current date.

    On subsequent calls, soil state is preserved and crops are reset
    so management decisions compound over multiple growing periods.
    """
    s = _get_session(game_id)
    if not s.field_manager.fields:
        raise HTTPException(400, "No fields configured")

    # On first call, store the base seed; subsequent calls vary by run_count.
    if s.run_count == 0:
        s.base_seed = seed
    effective_seed = s.base_seed + s.run_count

    # Reset crops and economics between runs (preserves soil state).
    if s.run_count > 0:
        _reset_all_crops(s)
        s.season_settled = False
        s.ledger.reset_season()

    start_date = s.current_date

    # Generate weather starting from the session's current date
    first_field = next(iter(s.field_manager.fields.values()))
    climate_key = first_field.patches[0].config.climate_key
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates[climate_key]
    gen = SyntheticWeatherGenerator(climate, seed=effective_seed)
    series = gen.generate(days, start_date)
    s.weather = series.records

    # Create turn manager for pause detection (uses first patch)
    first_patch = first_field.patches[0]
    tm = GameTurnManager(
        orch=first_patch.orch,
        weather=s.weather,
        plan=first_patch.orch.management_plan,
        pause_config=PauseConfig(),
        crop_key=first_patch.config.crop_key,
    )
    s.turn_manager = tm
    s.pause_events = []

    # Step ALL fields/patches each day
    from agrogame.soil.water.types import DailyDrivers as _DD

    tm.phase = SeasonPhase.EXECUTING
    for i, rec in enumerate(s.weather):
        drivers = _DD(rainfall_mm=rec.precip_mm or 0.0)
        s.field_manager.step_day(
            drivers=drivers,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
        tm.current_day = i + 1

    tm.phase = SeasonPhase.SETTLING
    grain = first_patch.orch.canopy.state.grain_biomass_g_m2
    from agrogame.game.turn import SeasonResult

    tm.result = SeasonResult(
        total_days=tm.current_day,
        grain_g_m2=grain,
        grain_kg_ha=grain * 10.0,
        pause_count=0,
        crop_key=tm.crop_key,
    )

    # Advance session date and run counter
    from datetime import timedelta

    end_date = start_date + timedelta(days=days)
    s.current_date = end_date
    s.run_count += 1

    # Build per-field, per-patch results with soil state
    field_results: dict[str, list[PatchResultResponse]] = {}
    for fid, fld in s.field_manager.fields.items():
        field_results[fid] = [
            PatchResultResponse(
                patch_idx=i,
                crop_key=p.config.crop_key,
                grain_g_m2=p.orch.canopy.state.grain_biomass_g_m2,
                grain_kg_ha=p.orch.canopy.state.grain_biomass_g_m2 * 10,
                soil_state=_build_soil_state(p),
            )
            for i, p in enumerate(fld.patches)
        ]

    return SeasonResultResponse(
        total_days=tm.current_day,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        season_number=s.run_count,
        pause_count=0,
        field_results=field_results,
    )


@router.get("/games/{game_id}/status", response_model=GameStatusResponse)
def get_status(game_id: str) -> GameStatusResponse:
    """Get current phase, pause events, or season result."""
    s = _get_session(game_id)
    phase = "planning"
    current_day = 0
    season_result = None

    if s.turn_manager:
        phase = s.turn_manager.phase.value
        current_day = s.turn_manager.current_day
        if s.turn_manager.result:
            r = s.turn_manager.result
            field_results: dict[str, list[PatchResultResponse]] = {}
            for fid, field in s.field_manager.fields.items():
                field_results[fid] = [
                    PatchResultResponse(
                        patch_idx=i,
                        crop_key=p.config.crop_key,
                        grain_g_m2=p.orch.canopy.state.grain_biomass_g_m2,
                        grain_kg_ha=p.orch.canopy.state.grain_biomass_g_m2 * 10,
                        soil_state=_build_soil_state(p),
                    )
                    for i, p in enumerate(field.patches)
                ]
            from datetime import timedelta

            end = s.current_date
            start = end - timedelta(days=r.total_days)
            season_result = SeasonResultResponse(
                total_days=r.total_days,
                start_date=start.isoformat(),
                end_date=end.isoformat(),
                season_number=s.run_count,
                pause_count=r.pause_count,
                field_results=field_results,
            )

    return GameStatusResponse(
        game_id=game_id,
        phase=phase,
        current_day=current_day,
        balance_credits=s.ledger.balance_credits,
        pause_events=[
            PauseEventResponse(day=pe.day, reason=pe.reason.value, message=pe.message)
            for pe in s.pause_events
        ],
        season_result=season_result,
    )


@router.post("/games/{game_id}/revise")
def revise_plan(game_id: str, req: ReviseRequest) -> dict:
    """Mid-season plan adjustment."""
    s = _get_session(game_id)
    if not s.turn_manager:
        raise HTTPException(400, "No active season")
    new_events = [
        ManagementEvent(day=e.day, action=e.action, params=e.params) for e in req.events
    ]
    s.turn_manager.revise_plan(req.from_day, new_events)
    return {"status": "revised", "from_day": req.from_day}


# ---------------------------------------------------------------------------
# Day-by-day game loop (#125)
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"irrigate", "fertilize", "plant", "harvest"}


def _compute_action_cost(action: str, params: dict, prices: PriceTable) -> int:
    """Compute action cost from PriceTable (data/economy/prices.yaml)."""
    if action == "irrigate":
        per_mm = prices.input_costs.get("irrigation_per_mm", 2)
        return int(per_mm * params.get("amount_mm", 20))
    if action == "fertilize":
        labor = prices.input_costs.get("labor_per_action", 50)
        fert_type = params.get("type", "urea")
        per_kg = prices.input_costs.get(f"fertilizer_{fert_type}", 1)
        amount = params.get("amount_kg_ha", 50)
        return int(labor + per_kg * amount)
    if action == "plant":
        crop_key = params.get("crop_key", "maize")
        return int(prices.input_costs.get(f"seed_{crop_key}", 200))
    if action == "harvest":
        return int(prices.input_costs.get("labor_per_action", 50))
    return 0


def _ensure_weather(s: GameSession, seed: int = 42) -> None:
    """Generate weather for the session if not yet generated."""
    if s.weather and s.day_index < len(s.weather):
        return
    first_field = next(iter(s.field_manager.fields.values()))
    climate_key = first_field.patches[0].config.climate_key
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates[climate_key]
    effective_seed = seed + s.run_count
    gen = SyntheticWeatherGenerator(climate, seed=effective_seed)
    series = gen.generate(s.season_days, s.current_date)
    s.weather = series.records
    s.season_active = True
    _maybe_inject_stress_weather(s)


def _maybe_inject_stress_weather(s: GameSession) -> None:
    """Inject extreme weather for debug stress testing.

    When debug/stress_weather is enabled, overwrite specific days with
    frost, heat wave, and heavy rain events for visual validation.
    """
    import os

    if not os.environ.get("AGROGAME_STRESS_WEATHER"):
        return
    for i, rec in enumerate(s.weather):
        # Every 3rd day: frost + heavy rain (always visible on any step)
        if i % 3 == 0 and i >= 10:
            rec.tmin_c = -5.0
            rec.tmax_c = 2.0
            rec.precip_mm = 80.0
        # Every 3rd day offset: heat wave
        elif i % 3 == 1 and i >= 10:
            rec.tmin_c = 25.0
            rec.tmax_c = 40.0


def _build_day_result(s: GameSession, rec: WeatherRecord) -> DayResultResponse:
    """Build the per-day response with weather, crop, and soil state."""

    weather = DayWeatherResponse(
        date=rec.day.isoformat() if rec.day else s.current_date.isoformat(),
        tmin_c=round(rec.tmin_c, 1),
        tmax_c=round(rec.tmax_c, 1),
        rain_mm=round(rec.precip_mm or 0.0, 1),
    )
    patches: dict[str, list[PatchDayResponse]] = {}
    for fid, fld in s.field_manager.fields.items():
        patches[fid] = []
        for i, p in enumerate(fld.patches):
            snap = p.orch.snapshot_soil()
            som_total = (
                sum(snap.som_labile_c)
                + sum(snap.som_intermediate_c)
                + sum(snap.som_stable_c)
            )
            theta_top = snap.water_theta[0] if snap.water_theta else 0.0
            # Actual plant water stress from transpiration supply/demand ratio
            w_stress = p.orch.canopy.state.last_water_stress
            patches[fid].append(
                PatchDayResponse(
                    patch_idx=i,
                    crop_key=p.config.crop_key,
                    crop_stage=p.orch.phenology.state.stage.value,
                    grain_g_m2=round(p.orch.canopy.state.grain_biomass_g_m2, 1),
                    root_depth_cm=round(p.orch.root_state.current_depth_cm, 1),
                    lai=round(p.orch.canopy.state.lai, 2),
                    soil_theta_surface=round(theta_top, 4),
                    som_total_c_g_m2=round(som_total, 1),
                    water_stress=round(w_stress, 2),
                    soil_state=_build_soil_state(p),
                    events=_serialize_events(p),
                )
            )
    # Check if crop reached maturity
    first_field = next(iter(s.field_manager.fields.values()))
    from agrogame.soil.phenology.types import PhenologyStage

    mature = (
        first_field.patches[0].orch.phenology.state.stage == PhenologyStage.MATURITY
    )
    season_done = mature or s.day_index >= len(s.weather)

    return DayResultResponse(
        day_number=s.day_index,
        date=s.current_date.isoformat(),
        weather=weather,
        patches=patches,
        season_complete=season_done,
        balance_credits=s.ledger.balance_credits,
    )


@router.post("/games/{game_id}/step", response_model=DayResultResponse)
def step_days(game_id: str, days: int = 1, seed: int = 42) -> DayResultResponse:
    """Advance the simulation by N days."""
    s = _get_session(game_id)
    if not s.field_manager.fields:
        raise HTTPException(400, "No fields configured")
    # If weather was consumed by /start-season, regenerate for new stepping
    if s.weather and s.day_index >= len(s.weather):
        s.weather = []
        s.day_index = 0
        _reset_all_crops(s)
        s.run_count += 1
        s.season_settled = False
        s.ledger.reset_season()
        s.turn_manager = None
    _ensure_weather(s, seed)

    from agrogame.soil.water.types import DailyDrivers as _DD
    from datetime import timedelta

    steps = min(days, len(s.weather) - s.day_index)
    if steps <= 0:
        raise HTTPException(400, "Season complete — no more days to simulate")

    from agrogame.api.models import DailySnapshot

    snapshots: list[DailySnapshot] = []
    last_rec = s.weather[s.day_index]
    for i in range(steps):
        idx = s.day_index + i
        if idx >= len(s.weather):
            break
        rec = s.weather[idx]
        last_rec = rec
        for fld in s.field_manager.fields.values():
            for p in fld.patches:
                p.recorder.clear()
                p.recorder.set_day(s.day_index + i)
        drivers = _DD(rainfall_mm=rec.precip_mm or 0.0)
        s.field_manager.step_day(
            drivers=drivers,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
        day_num = s.day_index + i + 1
        day_date = str(rec.day) if rec.day else ""
        for fid, fld in s.field_manager.fields.items():
            for pi, p in enumerate(fld.patches):
                snap = p.orch.snapshot_soil()
                n_total = sum(snap.n_no3) + sum(snap.n_nh4)
                theta_top = snap.water_theta[0] if snap.water_theta else 0.0
                patch_events = _serialize_events(p)
                snapshots.append(
                    DailySnapshot(
                        day_number=day_num,
                        date=day_date,
                        field_id=fid,
                        patch_idx=pi,
                        crop_stage=p.orch.phenology.state.stage.value,
                        lai=round(p.orch.canopy.state.lai, 2),
                        grain_g_m2=round(p.orch.canopy.state.grain_biomass_g_m2, 1),
                        water_stress=round(p.orch.canopy.state.last_water_stress, 2),
                        soil_theta_surface=round(theta_top, 4),
                        n_available_total=round(n_total, 1),
                        rain_mm=round(rec.precip_mm or 0.0, 1),
                        events=patch_events,
                    )
                )

    s.day_index += steps
    s.current_date = s.current_date + timedelta(days=steps)

    result = _build_day_result(s, last_rec)
    result.daily_snapshots = snapshots

    # Create SeasonResult when season completes so /report works
    if result.season_complete and (not s.turn_manager or not s.turn_manager.result):
        from agrogame.game.turn import GameTurnManager, SeasonResult

        first_field = next(iter(s.field_manager.fields.values()))
        first_patch = first_field.patches[0]
        grain = first_patch.orch.canopy.state.grain_biomass_g_m2
        if not s.turn_manager:
            s.turn_manager = GameTurnManager(
                orch=first_patch.orch,
                weather=s.weather,
                crop_key=first_patch.config.crop_key,
            )
        s.turn_manager.current_day = s.day_index
        s.turn_manager.result = SeasonResult(
            total_days=s.day_index,
            grain_g_m2=grain,
            grain_kg_ha=grain * 10.0,
            pause_count=0,
            crop_key=first_patch.config.crop_key,
        )
        s.run_count += 1

    return result


@router.post("/games/{game_id}/action", response_model=ActionResponse)
def execute_action(game_id: str, req: ActionRequest) -> ActionResponse:
    """Execute an immediate management action on the current day."""
    s = _get_session(game_id)
    if req.field_id not in s.field_manager.fields:
        raise HTTPException(404, f"Field {req.field_id} not found")
    if req.action not in _VALID_ACTIONS:
        raise HTTPException(400, f"Unknown action: {req.action}")

    from agrogame.game.economy import PriceTable

    prices = PriceTable.load()
    cost = _compute_action_cost(req.action, req.params, prices)

    if s.ledger.balance_credits < cost:
        raise HTTPException(
            400, f"Insufficient credits: need {cost}, have {s.ledger.balance_credits}"
        )

    s.ledger.record_cost(s.day_index, req.action, f"{req.action} {req.params}", cost)

    # Apply action
    field = s.field_manager.fields[req.field_id]
    if req.action == "plant":
        # Plant targets a specific patch (or all if no patch_idx given)
        crop_key = req.params.get("crop_key", "maize")
        patch_idx = req.params.get("patch_idx", -1)
        crops = load_crop_presets(Path("data/crops/presets.yaml"))
        for i, patch in enumerate(field.patches):
            if patch_idx >= 0 and i != int(patch_idx):
                continue
            climate_key = patch.config.climate_key
            preset = crops.get_preset(crop_key, climate_key)
            patch.orch.reset_crop(preset)
            # Re-subscribe recorder (reset_crop clears all event bus subscriptions)
            from agrogame.events.recorder import EventRecorder

            patch.recorder = EventRecorder(patch.orch.event_bus)
            patch.config = PatchConfig(
                soil_profile_key=patch.config.soil_profile_key,
                crop_key=crop_key,
                climate_key=climate_key,
                area_fraction=patch.config.area_fraction,
            )
    else:
        for patch in field.patches:
            if req.action == "irrigate":
                patch.orch.apply_irrigation(req.params.get("amount_mm", 20.0))
            elif req.action == "fertilize":
                patch.orch.apply_fertilizer(
                    req.params.get("type", "urea"),
                    req.params.get("amount_kg_ha", 50.0),
                )

    return ActionResponse(
        status="executed",
        action=req.action,
        cost_credits=cost,
        balance_credits=s.ledger.balance_credits,
        day_number=s.day_index,
    )


@router.get("/games/{game_id}/forecast", response_model=ForecastResponse)
def get_forecast(game_id: str, days: int = 5, seed: int = 42) -> ForecastResponse:
    """Peek ahead in the weather series for the next N days."""
    s = _get_session(game_id)
    _ensure_weather(s, seed)

    forecast: list[ForecastDayResponse] = []
    for i in range(days):
        idx = s.day_index + i
        if idx >= len(s.weather):
            break
        rec = s.weather[idx]
        forecast.append(
            ForecastDayResponse(
                date=rec.day.isoformat() if rec.day else "",
                tmin_c=round(rec.tmin_c, 1),
                tmax_c=round(rec.tmax_c, 1),
                rain_mm=round(rec.precip_mm or 0.0, 1),
            )
        )
    return ForecastResponse(current_day=s.day_index, forecast=forecast)


# ---------------------------------------------------------------------------
# Harvest report (#116)
# ---------------------------------------------------------------------------

# GYGA water-limited yield potentials (t/ha) — source: GYGA global dataset
_GYGA_YIELDS: dict[str, dict[str, float]] = {
    "maize": {
        "netherlands_temperate": 11.0,
        "kenya_highlands": 7.0,
        "sahel_arid": 3.0,
    },
    "sorghum": {"sahel_arid": 3.0},
    "spring_wheat": {
        "netherlands_temperate": 8.5,
        "kenya_highlands": 5.0,
    },
}


def _yield_grade(ratio: float) -> str:
    """Letter grade based on yield/GYGA ratio."""
    if ratio >= 0.90:
        return "A"
    if ratio >= 0.75:
        return "B"
    if ratio >= 0.60:
        return "C"
    if ratio >= 0.45:
        return "D"
    return "F"


@router.get("/games/{game_id}/report", response_model=HarvestReportResponse)
def get_harvest_report(game_id: str) -> HarvestReportResponse:
    """End-of-season harvest report with yield, GYGA grade, and P&L."""
    s = _get_session(game_id)
    if not s.turn_manager or not s.turn_manager.result:
        raise HTTPException(
            400, "No completed season — run /start-season or /step first"
        )

    from datetime import timedelta

    r = s.turn_manager.result
    end_date = s.current_date
    start_date = end_date - timedelta(days=r.total_days)

    # Settle season economics (idempotent — only once per season)
    prices = PriceTable.load()
    first_field = next(iter(s.field_manager.fields.values()))
    balance_before = s.ledger.balance_credits
    if not s.season_settled:
        total_grain = sum(
            p.orch.canopy.state.grain_biomass_g_m2 for p in first_field.patches
        ) / len(first_field.patches)
        s.ledger.settle_season(total_grain, r.crop_key, prices)
        s.season_settled = True
    balance_after = s.ledger.balance_credits

    # Build per-patch yield reports
    patch_reports: dict[str, list[PatchYieldReport]] = {}
    for fid, fld in s.field_manager.fields.items():
        patch_reports[fid] = []
        for i, p in enumerate(fld.patches):
            grain_g_m2 = p.orch.canopy.state.grain_biomass_g_m2
            grain_t_ha = grain_g_m2 / 100.0
            climate = p.config.climate_key
            gyga = _GYGA_YIELDS.get(p.config.crop_key, {}).get(climate, 10.0)
            ratio = min(grain_t_ha / gyga, 1.0) if gyga > 0 else 0.0
            snap = p.orch.snapshot_soil()
            som_total = (
                sum(snap.som_labile_c)
                + sum(snap.som_intermediate_c)
                + sum(snap.som_stable_c)
            )
            patch_reports[fid].append(
                PatchYieldReport(
                    patch_idx=i,
                    crop_key=p.config.crop_key,
                    soil_profile=p.config.soil_profile_key,
                    grain_t_ha=round(grain_t_ha, 2),
                    gyga_potential_t_ha=gyga,
                    yield_ratio=round(ratio, 3),
                    grade=_yield_grade(ratio),
                    som_total_c_g_m2=round(som_total, 1),
                    theta_surface=round(
                        snap.water_theta[0] if snap.water_theta else 0.0, 4
                    ),
                )
            )

    costs = [
        CostBreakdown(
            category=c.category,
            description=c.description,
            amount_credits=c.amount_credits,
        )
        for c in s.ledger.costs
    ]

    return HarvestReportResponse(
        season_number=s.run_count,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        total_days=r.total_days,
        patches=patch_reports,
        revenue_credits=s.ledger.season_revenue,
        costs=costs,
        total_cost_credits=s.ledger.season_costs,
        profit_credits=s.ledger.season_profit,
        balance_before=balance_before,
        balance_after=balance_after,
        balance_delta=balance_after - balance_before,
    )


# Save directory — configurable via environment or default
_SAVE_DIR = Path(os.environ.get("AGROGAME_SAVE_DIR", "saves"))


@router.post("/games/{game_id}/save")
def save_game(game_id: str) -> dict:
    """Save game state to disk as JSON with checksum."""
    s = _get_session(game_id)

    from agrogame.game.save import GameState, save_to_file

    state = GameState(
        game_id=game_id,
        field_manager_data=s.field_manager.to_dict(),
        ledger_data=s.ledger.to_dict(),
        weather_data=[w.to_dict() for w in s.weather],
        current_date=s.current_date.isoformat(),
        base_seed=s.base_seed,
        run_count=s.run_count,
        day_index=s.day_index,
        season_days=s.season_days,
        season_active=s.season_active,
        season_settled=s.season_settled,
    )
    path = _SAVE_DIR / f"{game_id}.agrosave.json"
    save_to_file(state, path)
    return {"status": "saved", "game_id": game_id, "path": str(path)}


@router.post("/games/{game_id}/load")
def load_game(game_id: str) -> dict:
    """Load game state from a save file on disk."""
    from agrogame.game.save import load_from_file

    path = _SAVE_DIR / f"{game_id}.agrosave.json"
    if not path.exists():
        raise HTTPException(404, f"No save found for {game_id}")
    try:
        state = load_from_file(path)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    kwargs = state.to_session_kwargs()
    session = GameSession(**kwargs)
    games[game_id] = session
    return {"status": "loaded", "game_id": game_id}
