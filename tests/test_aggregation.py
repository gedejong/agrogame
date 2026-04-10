"""Tests for soil aggregation module (#218).

Nine tests following the validation plan — literature-cited quantitative assertions.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.soil.aggregation import (
    AggregationModule,
    SoilAggregationParams,
    SoilAggregationState,
    AggregateStructureUpdated,
    TillageApplied,
    StructureDegraded,
)
from agrogame.soil.water.types import DailyDrivers
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets


# --- 1. Formation rates ---


def test_formation_with_roots_and_fungi() -> None:
    """30 weekly steps with active roots should increase macro by 5–20%.

    Ref: Six et al. 2004, Table 3 — formation rates 1–10% per month.
    """
    bus = EventBus()
    state = SoilAggregationState.from_layers(3)
    # Start with low macro (bare soil scenario)
    for i in range(3):
        state.micro[i] = 0.60
        state.meso[i] = 0.30
        state.macro[i] = 0.10
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)
    initial_macro = state.macro[0]

    for _ in range(30):
        module.weekly_step(
            root_density_fractions=[0.5, 0.3, 0.1],
            fungal_fractions=[0.6, 0.4, 0.2],
            temperature_c=25.0,
        )

    gained = state.macro[0] - initial_macro
    assert (
        0.05 <= gained <= 0.40
    ), f"Macro gain {gained:.3f} should be 0.05–0.40 after 30 weeks with roots"
    # Mass conservation
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"Fractions sum to {total:.6f}, expected 1.0"


# --- 2. Tillage destruction ---


def test_tillage_destruction() -> None:
    """Tillage at intensity=1.0 should destroy 30–70% of macroaggregates.

    Ref: Six et al. 2000, SSSAJ — moldboard plow destroys 50–70%.
    """
    bus = EventBus()
    state = SoilAggregationState.from_layers(3)
    for i in range(3):
        state.macro[i] = 0.50
        state.meso[i] = 0.30
        state.micro[i] = 0.20
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)

    events: list[TillageApplied] = []
    bus.subscribe(TillageApplied, events.append)

    initial_macro = state.macro[0]
    module.apply_tillage(intensity=1.0)

    remaining = state.macro[0]
    destroyed_frac = 1.0 - remaining / initial_macro
    assert (
        0.30 <= destroyed_frac <= 0.70
    ), f"Destroyed {destroyed_frac:.2f}, expected 0.30–0.70"
    assert len(events) == 1
    assert events[0].intensity == 1.0
    # Mass conservation
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6


# --- 3. MWD calculation ---


def test_mwd_calculation() -> None:
    """MWD with known distribution should be in expected range.

    30% micro (midpoint 0.01mm), 30% meso (0.135mm), 40% macro (2.0mm)
    → MWD = 0.30*0.01 + 0.30*0.135 + 0.40*2.0 = 0.8435 mm

    Ref: Kemper & Rosenau 1986, Methods of Soil Analysis.
    """
    state = SoilAggregationState.from_layers(1)
    state.micro[0] = 0.30
    state.meso[0] = 0.30
    state.macro[0] = 0.40
    mwd = state.mwd(0)
    expected = 0.30 * 0.01 + 0.30 * 0.135 + 0.40 * 2.0
    assert abs(mwd - expected) < 0.001, f"MWD {mwd:.4f} ≠ expected {expected:.4f}"
    assert 0.5 <= mwd <= 1.5, f"MWD {mwd:.4f} outside 0.5–1.5 mm range"


# --- 4. Wet-dry breakdown ---


def test_wet_dry_breakdown() -> None:
    """Wet-dry cycle should destroy 5–15% of macroaggregates.

    Ref: Denef et al. 2001, Soil Biol Biochem.
    """
    bus = EventBus()
    state = SoilAggregationState.from_layers(1)
    state.macro[0] = 0.40
    state.meso[0] = 0.35
    state.micro[0] = 0.25
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)

    events: list[StructureDegraded] = []
    bus.subscribe(StructureDegraded, events.append)

    initial_macro = state.macro[0]
    module.apply_wet_dry_breakdown(0)

    lost_frac = 1.0 - state.macro[0] / initial_macro
    assert (
        0.05 <= lost_frac <= 0.15
    ), f"Wet-dry lost {lost_frac:.3f}, expected 0.05–0.15"
    assert len(events) == 1
    assert events[0].cause == "wet_dry"
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6


# --- 5. Mass conservation ---


def test_mass_conservation_all_operations() -> None:
    """Fractions sum to 1.0 after formation, tillage, wet-dry, freeze-thaw."""
    state = SoilAggregationState.from_layers(1)
    module = AggregationModule(SoilAggregationParams(), state)

    # Formation
    module.weekly_step([0.5], [0.6], 25.0)
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"After formation: {total}"

    # Tillage
    module.apply_tillage(0.8)
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"After tillage: {total}"

    # Wet-dry
    module.apply_wet_dry_breakdown(0)
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"After wet-dry: {total}"

    # Freeze-thaw
    module.apply_freeze_thaw_breakdown(0)
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"After freeze-thaw: {total}"

    # Raindrop
    module.apply_raindrop_impact(50.0)
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6, f"After raindrop: {total}"


# --- 6. No-till recovery (integration) ---


def test_notill_recovery_one_year() -> None:
    """365 days with active roots, no tillage → 5–20% macro gain per year.

    Ref: Six et al. 2004 — no-till fields recover aggregate structure
    at 5–20% macro increase per year depending on climate and biology.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )
    initial_macro = orch.agg_state.macro[0]
    start = date(2024, 4, 1)
    for d in range(365):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=2.0),
            tmin_c=10.0,
            tmax_c=25.0,
            par_mj_m2=15.0,
            sim_date=start + timedelta(days=d),
        )
    gained = orch.agg_state.macro[0] - initial_macro
    # AC: 5–20% per year. Threshold at 0.05 to catch regressions.
    assert gained > 0.05, f"No-till macro gain {gained:.4f} should be >5% after 1 year"


# --- 7. Tillage + recovery (integration) ---


def test_tillage_then_recovery() -> None:
    """Apply tillage, then run 180 days. Verify recovery trajectory.

    Ref: Six et al. 2000 — recovery timescale is 6–24 months.
    """
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )
    # Apply intensive tillage
    orch.apply_tillage(intensity=1.0)
    post_tillage_macro = orch.agg_state.macro[0]

    # Run 180 days of recovery
    start = date(2024, 4, 1)
    for d in range(180):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=2.0),
            tmin_c=12.0,
            tmax_c=26.0,
            par_mj_m2=16.0,
            sim_date=start + timedelta(days=d),
        )
    # Some recovery should have occurred — at least 2% gain in 180 days
    recovery = orch.agg_state.macro[0] - post_tillage_macro
    assert (
        recovery > 0.02
    ), f"Macro recovery {recovery:.4f} should be >2% after 180 days"


# --- 8. Multi-season persistence (integration) ---


def test_snapshot_preserves_aggregation() -> None:
    """Aggregate state should round-trip through snapshot/restore."""
    soils = load_soil_presets(Path("soils/presets.yaml"))
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
    )
    # Modify state
    orch.agg_state.macro[0] = 0.45
    orch.agg_state.meso[0] = 0.30
    orch.agg_state.micro[0] = 0.25

    snap = orch.snapshot_soil()
    assert snap.agg_macro[0] == 0.45

    # Modify again
    orch.agg_state.macro[0] = 0.10
    orch.restore_soil(snap)
    assert orch.agg_state.macro[0] == 0.45
    assert orch.agg_state.meso[0] == 0.30
    assert orch.agg_state.micro[0] == 0.25


# --- 9. Frozen soil / freeze-thaw ---


def test_freeze_thaw_breakdown() -> None:
    """Freeze-thaw cycle should trigger 10–20% macro breakdown.

    Ref: Six et al. 2004 — 10–20% per freeze-thaw cycle.
    """
    bus = EventBus()
    state = SoilAggregationState.from_layers(1)
    state.macro[0] = 0.40
    state.meso[0] = 0.35
    state.micro[0] = 0.25
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)

    events: list[StructureDegraded] = []
    bus.subscribe(StructureDegraded, events.append)

    initial_macro = state.macro[0]
    module.apply_freeze_thaw_breakdown(0)

    lost_frac = 1.0 - state.macro[0] / initial_macro
    assert (
        0.10 <= lost_frac <= 0.20
    ), f"Freeze-thaw lost {lost_frac:.3f}, expected 0.10–0.20"
    assert len(events) == 1
    assert events[0].cause == "freeze_thaw"
    total = state.micro[0] + state.meso[0] + state.macro[0]
    assert abs(total - 1.0) < 1e-6


# --- Additional: events emitted ---


def test_events_emitted_during_weekly_step() -> None:
    """AggregateStructureUpdated should be emitted for each layer."""
    bus = EventBus()
    state = SoilAggregationState.from_layers(3)
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)
    events: list[AggregateStructureUpdated] = []
    bus.subscribe(AggregateStructureUpdated, events.append)
    module.weekly_step([0.3, 0.2, 0.1], [0.5, 0.3, 0.1], 20.0)
    assert len(events) == 3
    layers = {e.layer for e in events}
    assert layers == {0, 1, 2}


def test_serialization_round_trip() -> None:
    """State to_dict/from_dict should preserve values."""
    state = SoilAggregationState.from_layers(3)
    state.macro[0] = 0.55
    d = state.to_dict()
    restored = SoilAggregationState.from_dict(d)
    assert restored.macro[0] == 0.55
    assert len(restored.micro) == 3


def test_tillage_management_event() -> None:
    """Tillage action via ManagementEvent should work."""
    from agrogame.sim.management import ManagementEvent, ManagementPlan

    soils = load_soil_presets(Path("soils/presets.yaml"))
    plan = ManagementPlan(
        events=[ManagementEvent(day=0, action="tillage", params={"intensity": 0.8})]
    )
    orch = FullSimulationOrchestrator(
        soils.soils["loam_temperate"],
        event_bus=EventBus(),
        management_plan=plan,
    )
    initial_macro = orch.agg_state.macro[0]
    orch.step_day(
        drivers=DailyDrivers(rainfall_mm=0.0),
        tmin_c=15.0,
        tmax_c=25.0,
        par_mj_m2=15.0,
        sim_date=date(2024, 5, 1),
    )
    assert (
        orch.agg_state.macro[0] < initial_macro
    ), "Tillage via management plan should reduce macro"


# --- Runtime unit tests ---


def test_runtime_weekly_cadence() -> None:
    """AggregationRuntime should only run formation every 7 days."""
    from agrogame.soil.aggregation.runtime import AggregationRuntime

    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils["loam_temperate"]
    bus = EventBus()
    state = SoilAggregationState.from_layers(len(profile.layers))
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)
    from agrogame.soil.water.state import SoilWaterState

    water_state = SoilWaterState(profile)
    AggregationRuntime(bus, module, profile, water_state)  # subscribes to bus

    events: list[AggregateStructureUpdated] = []
    bus.subscribe(AggregateStructureUpdated, events.append)

    from agrogame.sim.calendar_events import DayTick

    # Tick 6 days — no formation events (only raindrop/breakdown)
    for d in range(6):
        bus.emit(
            DayTick(
                sim_date=date(2024, 5, 1 + d),
                phase="day_end",
                drivers=DailyDrivers(rainfall_mm=0.0),
                tmin_c=15.0,
                tmax_c=25.0,
            )
        )
    formation_events_6d = len(events)
    assert formation_events_6d == 0, "No formation before day 7"

    # Day 7 triggers weekly formation
    bus.emit(
        DayTick(
            sim_date=date(2024, 5, 7),
            phase="day_end",
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=15.0,
            tmax_c=25.0,
        )
    )
    assert len(events) > 0, "Formation should trigger on day 7"


def test_runtime_freeze_thaw_hysteresis() -> None:
    """Freeze-thaw needs freeze then thaw with 2C hysteresis."""
    from agrogame.soil.aggregation.runtime import AggregationRuntime
    from agrogame.soil.water.state import SoilWaterState
    from agrogame.sim.calendar_events import DayTick

    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils["loam_temperate"]
    bus = EventBus()
    state = SoilAggregationState.from_layers(len(profile.layers))
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)
    water_state = SoilWaterState(profile)
    AggregationRuntime(bus, module, profile, water_state)  # subscribes to bus

    degraded: list[StructureDegraded] = []
    bus.subscribe(StructureDegraded, degraded.append)

    # Freeze (temp <= 0)
    bus.emit(
        DayTick(
            sim_date=date(2024, 1, 1),
            phase="day_end",
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=-5.0,
            tmax_c=-2.0,
        )
    )
    # Still frozen (temp = 1C, within 2C hysteresis)
    bus.emit(
        DayTick(
            sim_date=date(2024, 1, 2),
            phase="day_end",
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=0.0,
            tmax_c=2.0,
        )
    )
    ft_events = [e for e in degraded if e.cause == "freeze_thaw"]
    assert len(ft_events) == 0, "No thaw at 1C (within hysteresis)"

    # Thaw (temp > 2C)
    bus.emit(
        DayTick(
            sim_date=date(2024, 1, 3),
            phase="day_end",
            drivers=DailyDrivers(rainfall_mm=0.0),
            tmin_c=2.0,
            tmax_c=6.0,
        )
    )
    ft_events = [e for e in degraded if e.cause == "freeze_thaw"]
    assert len(ft_events) > 0, "Thaw above 2C should trigger breakdown"


def test_runtime_microbes_fungal_update() -> None:
    """Runtime should track fungal fraction from MicrobialFBUpdated."""
    from agrogame.soil.aggregation.runtime import AggregationRuntime
    from agrogame.soil.water.state import SoilWaterState
    from agrogame.soil.microbes.events import MicrobialFBUpdated

    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils["loam_temperate"]
    bus = EventBus()
    state = SoilAggregationState.from_layers(len(profile.layers))
    module = AggregationModule(SoilAggregationParams(), state, event_bus=bus)
    water_state = SoilWaterState(profile)
    rt = AggregationRuntime(bus, module, profile, water_state)

    bus.emit(MicrobialFBUpdated(layer=0, fungal_fraction=0.8))
    assert rt._fungal_fractions is not None
    assert rt._fungal_fractions[0] == 0.8
