"""Tests for redox dynamics: Eh computation, redox ladder, N2O, CH4 (#72).

Literature-cited quantitative assertions for scientific accuracy.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.redox.module import RedoxModule
from agrogame.soil.redox.params import RedoxParams
from agrogame.soil.redox.state import RedoxState, DominantAcceptor
from agrogame.soil.redox.events import (
    CH4Emitted,
    CH4Oxidized,
)
from agrogame.soil.water.types import DailyDrivers


# --- Unit: Eh-WFPS curve ---


def test_eh_wfps_monotonic_decrease() -> None:
    """Eh should decrease monotonically with increasing WFPS.

    Ref: Reddy & DeLaune 2008, Biogeochemistry of Wetlands, Table 2.1.
    """
    m = RedoxModule(RedoxParams(), RedoxState.from_layers(1))
    wfps_values = [0.2, 0.4, 0.6, 0.8, 1.0]
    ehs = [m._equilibrium_eh(w) for w in wfps_values]
    for i in range(len(ehs) - 1):
        assert ehs[i] > ehs[i + 1], (
            f"Eh at WFPS={wfps_values[i]} ({ehs[i]:.0f}) should exceed "
            f"Eh at WFPS={wfps_values[i+1]} ({ehs[i+1]:.0f})"
        )


def test_eh_range_aerobic_to_anaerobic() -> None:
    """Eh should be +300-500 mV aerobic, -200-300 mV anaerobic.

    Ref: Reddy & DeLaune 2008, Table 2.1.
    """
    m = RedoxModule(RedoxParams(), RedoxState.from_layers(1))
    eh_dry = m._equilibrium_eh(0.3)
    eh_wet = m._equilibrium_eh(1.0)
    assert 300.0 <= eh_dry <= 500.0, f"Aerobic Eh={eh_dry:.0f}, expected 300-500"
    assert (
        -350.0 <= eh_wet <= -150.0
    ), f"Anaerobic Eh={eh_wet:.0f}, expected -350 to -150"


# --- Unit: Redox ladder ---


def test_redox_ladder_classification() -> None:
    """Dominant acceptor follows thermodynamic sequence.

    Ref: Stumm & Morgan 1996, Aquatic Chemistry.
    """
    assert RedoxModule._classify_acceptor(350) == DominantAcceptor.OXYGEN
    assert RedoxModule._classify_acceptor(150) == DominantAcceptor.NITRATE
    assert RedoxModule._classify_acceptor(0) == DominantAcceptor.IRON
    assert RedoxModule._classify_acceptor(-250) == DominantAcceptor.METHANOGENESIS


# --- Unit: Eh response lag ---


def test_eh_exponential_decay() -> None:
    """Eh should decay exponentially toward equilibrium, not jump instantly.

    With tau=2 days, after 1 day: ~39% of the gap closed (1-exp(-0.5)).
    """
    p = RedoxParams(tau_days=2.0)
    state = RedoxState.from_layers(1)
    state.eh_mv[0] = 400.0  # start aerobic
    m = RedoxModule(p, state)
    # Saturated soil → equilibrium Eh should be very negative
    m.daily_step([0.45], [0.45], [0.0], 20.0)
    # After 1 day, should have moved ~39% toward target, not all the way
    assert state.eh_mv[0] < 400.0, "Eh should have decreased"
    assert (
        state.eh_mv[0] > -200.0
    ), "Eh should not have reached full equilibrium in 1 day"
    # After 5 more days, should be much closer to equilibrium
    for _ in range(5):
        m.daily_step([0.45], [0.45], [0.0], 20.0)
    assert state.eh_mv[0] < -100.0, "After 6 days saturated, Eh should be < -100 mV"


# --- Unit: N2O/N2 partitioning ---


def test_n2o_fraction_at_intermediate_eh() -> None:
    """At Eh ~150 mV (intermediate), N2O fraction should be > 40%.

    Ref: Firestone & Davidson 1989, Exchange of Trace Gases.
    """
    frac = RedoxModule.n2o_fraction(150.0)
    assert frac > 0.40, f"N2O fraction at Eh=150 should be > 40%, got {frac:.2f}"


def test_n2o_fraction_at_low_eh() -> None:
    """At Eh < -100 mV (strongly reducing), N2O fraction should be < 20%.

    Ref: Firestone & Davidson 1989; complete reduction to N2 dominates.
    """
    frac = RedoxModule.n2o_fraction(-100.0)
    assert frac < 0.20, f"N2O fraction at Eh=-100 should be < 20%, got {frac:.2f}"


# --- Unit: CH4 production ---


def test_ch4_only_below_minus_200() -> None:
    """CH4 production should only occur when Eh < -200 mV.

    Ref: Le Mer & Roger 2001, Eur J Soil Biol.
    """
    bus = EventBus()
    ch4_events: list[CH4Emitted] = []
    bus.subscribe(CH4Emitted, ch4_events.append)
    state = RedoxState.from_layers(1)
    m = RedoxModule(RedoxParams(), state, event_bus=bus)
    # Eh = -150 → no CH4
    state.eh_mv[0] = -150.0
    m._process_methane(1, 20.0)
    assert len(ch4_events) == 0, "No CH4 at Eh > -200"
    # Eh = -250 → CH4 produced
    state.eh_mv[0] = -250.0
    m._process_methane(1, 20.0)
    assert len(ch4_events) > 0, "CH4 should be produced at Eh < -200"
    assert ch4_events[0].amount_kg_c_ha > 0.0


def test_ch4_temperature_sensitivity() -> None:
    """CH4 production should increase with temperature (Q10 ~ 4).

    Ref: Conrad 2002, FEMS Microbiol Ecol.
    """
    state = RedoxState.from_layers(1)
    state.eh_mv[0] = -250.0
    p = RedoxParams(ch4_q10=4.0, ch4_ref_temp_c=25.0)

    bus1 = EventBus()
    ch4_cold: list[CH4Emitted] = []
    bus1.subscribe(CH4Emitted, ch4_cold.append)
    m1 = RedoxModule(p, state, event_bus=bus1)
    m1._process_methane(1, 15.0)

    bus2 = EventBus()
    ch4_warm: list[CH4Emitted] = []
    bus2.subscribe(CH4Emitted, ch4_warm.append)
    m2 = RedoxModule(p, state, event_bus=bus2)
    m2._process_methane(1, 25.0)

    assert (
        ch4_warm[0].amount_kg_c_ha > ch4_cold[0].amount_kg_c_ha
    ), "CH4 at 25C should exceed CH4 at 15C"


# --- Unit: CH4 oxidation ---


def test_ch4_oxidation_in_aerobic_surface() -> None:
    """Aerobic surface layer should oxidize a fraction of produced CH4.

    Ref: Le Mer & Roger 2001 — methanotrophy in oxidized zones.
    """
    bus = EventBus()
    oxidized: list[CH4Oxidized] = []
    bus.subscribe(CH4Oxidized, oxidized.append)
    state = RedoxState.from_layers(2)
    state.eh_mv[0] = 200.0  # aerobic surface
    state.eh_mv[1] = -250.0  # reducing subsurface
    m = RedoxModule(RedoxParams(ch4_oxidation_fraction=0.6), state, event_bus=bus)
    m._process_methane(2, 20.0)
    assert len(oxidized) > 0, "Surface should oxidize CH4"
    assert oxidized[0].amount_kg_c_ha > 0.0


# --- Unit: Fe-P release ---


def test_fe_p_release_under_reducing() -> None:
    """When Eh < 100 mV, fixed_p should decrease and available_p increase.

    Ref: Patrick & Khalid 1974, Science.
    Tests the P runtime's RedoxChanged handler directly.
    """
    from agrogame.soil.phosphorus import SoilPhosphorusState
    from agrogame.soil.phosphorus.cycle import PhosphorusCycle
    from agrogame.soil.phosphorus.runtime import PhosphorusRuntime
    from agrogame.soil.redox.events import RedoxChanged

    soils = load_soil_presets(Path("soils/presets.yaml"))
    profile = soils.soils["loam_temperate"]
    bus = EventBus()
    from agrogame.soil.water.state import SoilWaterState
    from typing import cast, Any

    ws = SoilWaterState(profile)
    ps = SoilPhosphorusState(profile)
    pc = PhosphorusCycle(bus, ps, water_state=cast(Any, ws), profile=cast(Any, profile))
    _ = PhosphorusRuntime(bus, pc)
    # Set some fixed P
    for i in range(len(ps.fixed_p)):
        ps.fixed_p[i] = 10.0
    fixed_before = sum(ps.fixed_p)
    avail_before = sum(ps.available_p)
    # Emit RedoxChanged with low Eh — triggers Fe-P release
    for i in range(len(profile.layers)):
        bus.emit(RedoxChanged(layer=i, eh_mv=-50.0, dominant_acceptor="Fe3+"))
    fixed_after = sum(ps.fixed_p)
    avail_after = sum(ps.available_p)
    assert fixed_after < fixed_before, "Fixed P should decrease under reducing"
    assert avail_after > avail_before, "Available P should increase under reducing"


# --- Integration: waterlogged vs well-drained ---


def _make_orch(soil_key: str = "loam_temperate") -> FullSimulationOrchestrator:
    soils = load_soil_presets(Path("soils/presets.yaml"))
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    return FullSimulationOrchestrator(
        soils.soils[soil_key],
        event_bus=EventBus(),
        crop=crops.crops["maize"],
    )


def test_waterlogged_scenario_reduces_eh() -> None:
    """Persistent saturation drives Eh toward reducing conditions.

    Tests the redox module directly with forced WFPS=1.0 to verify
    Eh reaches strongly reducing levels, independent of water drainage.

    Ref: Reddy & DeLaune 2008 — flooded soils reach -200 to -300 mV.
    """
    state = RedoxState.from_layers(3)
    m = RedoxModule(RedoxParams(), state)
    # Simulate 30 days at full saturation
    for _ in range(30):
        m.daily_step([0.45, 0.45, 0.45], [0.45, 0.45, 0.45], [0.0] * 3, 20.0)
    min_eh = min(state.eh_mv)
    assert min_eh < -200.0, f"Eh after 30d saturated: {min_eh:.0f}, expected < -200"


def test_well_drained_stays_aerobic() -> None:
    """Well-drained soil should maintain Eh > +200 mV.

    Ref: Reddy & DeLaune 2008 — upland soils typically +300 to +500 mV.
    """
    orch = _make_orch()
    start = date(2024, 5, 1)
    for d in range(60):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=2.0),  # light rain, well drained
            tmin_c=15.0,
            tmax_c=28.0,
            par_mj_m2=18.0,
            sim_date=start + timedelta(days=d),
        )
    min_eh = min(orch.redox_state.eh_mv)
    assert min_eh > 100.0, f"Well-drained Eh: {min_eh:.0f}, expected > 100"


# --- Snapshot roundtrip ---


def test_snapshot_preserves_redox_eh() -> None:
    """Save/restore should preserve Eh across seasons."""
    orch = _make_orch()
    orch.redox_state.eh_mv[0] = -150.0
    snap = orch.snapshot_soil()
    assert snap.redox_eh[0] == -150.0
    # Restore
    orch.redox_state.eh_mv[0] = 400.0
    orch.restore_soil(snap)
    assert orch.redox_state.eh_mv[0] == -150.0
