"""FastAPI routes for the game API (ADR-005, AGRO-111)."""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException

from agrogame.api.models import (
    CreateGameRequest,
    GameCreatedResponse,
    GameStatusResponse,
    PatchResultResponse,
    PauseEventResponse,
    PlanRequest,
    ReviseRequest,
    SeasonResultResponse,
    SoilStateResponse,
)
from agrogame.api.state import GameSession, games
from agrogame.game.economy import EconomicLedger
from agrogame.game.field import FieldManager, Patch, PatchConfig
from agrogame.game.turn import GameTurnManager, PauseConfig, SeasonPhase
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

router = APIRouter(prefix="/api/v1")


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
    """Run the season synchronously, stepping all fields/patches."""
    s = _get_session(game_id)
    if not s.field_manager.fields:
        raise HTTPException(400, "No fields configured")

    # Generate weather from first field's climate
    first_field = next(iter(s.field_manager.fields.values()))
    climate_key = first_field.patches[0].config.climate_key
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates[climate_key]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, date(2024, 4, 1))
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

    # Step ALL fields/patches each day (not just first patch)
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
            season_result = SeasonResultResponse(
                total_days=r.total_days,
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


# In-memory save slots — disk persistence deferred to AGRO-36
_save_slots: dict[str, dict] = {}


@router.post("/games/{game_id}/save")
def save_game(game_id: str) -> dict:
    """Save game state to an in-memory slot."""
    s = _get_session(game_id)
    _save_slots[game_id] = {
        "field_manager": s.field_manager.to_dict(),
        "ledger": s.ledger.to_dict(),
        "game_id": game_id,
    }
    return {"status": "saved", "game_id": game_id}


@router.post("/games/{game_id}/load")
def load_game(game_id: str) -> dict:
    """Load game state from an in-memory save slot."""
    if game_id not in _save_slots:
        raise HTTPException(404, f"No save found for {game_id}")
    save = _save_slots[game_id]
    fm = FieldManager.from_dict(save["field_manager"])
    ledger = EconomicLedger.from_dict(save["ledger"])
    session = GameSession(game_id=game_id, field_manager=fm, ledger=ledger)
    games[game_id] = session
    return {"status": "loaded", "game_id": game_id}
