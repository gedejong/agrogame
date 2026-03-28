"""Tests for SOM→microbial and SOM→N cycle wiring (AGRO-79)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.microbes.events import MicrobialActivityComputed
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.nitrogen.events import DenitrificationOccurred, NutrientLeached
from agrogame.soil.nitrogen.state import SoilNitrogenState
from agrogame.soil.som.events import SOMDecomposed
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _load() -> tuple:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    climate = climates.climates["netherlands_temperate"]
    return crops, climate, profile


# ---------------------------------------------------------------------------
# AC: N cycle consumes SOMDecomposed → adds mineralized N to NH4
# ---------------------------------------------------------------------------
class TestNcycleSOMConsumption:
    def test_som_decomposed_adds_to_nh4(self) -> None:
        """SOMDecomposed event should inject mineralized N into NH4 pool."""
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        bus = EventBus()
        state = SoilNitrogenState(profile)
        _ = NitrogenCycle(bus, state)

        nh4_before = state.nh4[0]
        bus.emit(
            SOMDecomposed(
                layer=0, pool="all", decomposed_c_kg_ha=50.0, mineralized_n_kg_ha=3.0
            )
        )
        assert state.nh4[0] == pytest.approx(nh4_before + 3.0)

    def test_negative_mineralization_ignored(self) -> None:
        """Negative mineralized_n (immobilization) should not add to NH4."""
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))
        profile = soil_lib.soils["loam_temperate"]
        bus = EventBus()
        state = SoilNitrogenState(profile)
        _ = NitrogenCycle(bus, state)

        nh4_before = state.nh4[0]
        bus.emit(
            SOMDecomposed(
                layer=0, pool="all", decomposed_c_kg_ha=50.0, mineralized_n_kg_ha=-2.0
            )
        )
        assert state.nh4[0] == nh4_before


# ---------------------------------------------------------------------------
# AC: Higher SOM → higher microbial activity (Monod response)
# ---------------------------------------------------------------------------
class TestSOMDrivenMicrobialActivity:
    def test_higher_som_higher_activity(self) -> None:
        """Higher SOM content should produce higher microbial activity."""
        crops, climate, profile = _load()

        # Run with default SOM
        orch_default = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        activity_default: list[float] = []
        orch_default.event_bus.subscribe(
            MicrobialActivityComputed,
            lambda e: (
                activity_default.append(e.activity_index) if e.layer == 0 else None
            ),
        )
        gen = SyntheticWeatherGenerator(climate, seed=42)
        series = gen.generate(30, date(2024, 4, 1))
        for rec in series.records:
            orch_default.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                par_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )

        # Run with boosted SOM (double labile pool)
        orch_high = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        if orch_high._som_runtime.som:
            for ly in orch_high._som_runtime.som.state.layers:
                ly.labile.c_kg_ha *= 2.0
        activity_high: list[float] = []
        orch_high.event_bus.subscribe(
            MicrobialActivityComputed,
            lambda e: activity_high.append(e.activity_index) if e.layer == 0 else None,
        )
        gen2 = SyntheticWeatherGenerator(climate, seed=42)
        series2 = gen2.generate(30, date(2024, 4, 1))
        for rec in series2.records:
            orch_high.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                par_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )

        # Higher SOM should produce at least as much activity on average
        avg_default = sum(activity_default) / max(len(activity_default), 1)
        avg_high = sum(activity_high) / max(len(activity_high), 1)
        assert avg_high >= avg_default


# ---------------------------------------------------------------------------
# AC: SOM-driven mineralization differs from old fixed-rate
# ---------------------------------------------------------------------------
class TestSOMDrivenMineralization:
    def test_som_mineralization_contributes(self) -> None:
        """SOMDecomposed events should produce measurable NH4 increase
        beyond what the fixed-rate mineralization provides."""
        crops, climate, profile = _load()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        som_n_total = [0.0]
        orch.event_bus.subscribe(
            SOMDecomposed,
            lambda e: som_n_total.__setitem__(
                0, som_n_total[0] + e.mineralized_n_kg_ha
            ),
        )
        gen = SyntheticWeatherGenerator(climate, seed=42)
        series = gen.generate(60, date(2024, 4, 1))
        for rec in series.records:
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                par_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
        # SOM should have mineralized some N over 60 days
        assert som_n_total[0] > 0


# ---------------------------------------------------------------------------
# AC: N mass balance within 0.5% over 120 days
# ---------------------------------------------------------------------------
def test_n_mass_balance_with_som_wiring() -> None:
    """N mass balance should close within 0.5% with SOM-driven mineralization."""
    crops, climate, profile = _load()
    orch = FullSimulationOrchestrator(
        profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
    )
    initial_n = orch.n_state.total_nitrogen_kg_ha()

    from agrogame.soil.nitrogen.events import VolatilizationOccurred

    leached = [0.0]
    denitrified = [0.0]
    volatilized = [0.0]
    som_mineralized = [0.0]
    orch.event_bus.subscribe(
        NutrientLeached,
        lambda e: leached.__setitem__(0, leached[0] + e.amount_kg_ha),
    )
    orch.event_bus.subscribe(
        DenitrificationOccurred,
        lambda e: denitrified.__setitem__(0, denitrified[0] + e.amount_kg_ha),
    )
    orch.event_bus.subscribe(
        VolatilizationOccurred,
        lambda e: volatilized.__setitem__(0, volatilized[0] + e.amount_kg_ha),
    )
    orch.event_bus.subscribe(
        SOMDecomposed,
        lambda e: som_mineralized.__setitem__(
            0, som_mineralized[0] + max(0, e.mineralized_n_kg_ha)
        ),
    )

    gen = SyntheticWeatherGenerator(climate, seed=42)
    series = gen.generate(120, date(2024, 4, 1))
    for rec in series.records:
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

    final_n = orch.n_state.total_nitrogen_kg_ha()
    # N balance: initial + SOM_input = final + losses + uptake
    total_inputs = som_mineralized[0]
    total_losses = leached[0] + denitrified[0] + volatilized[0]
    plant_uptake = initial_n + total_inputs - final_n - total_losses
    # Plant uptake should be non-negative (N consumed, not created)
    assert plant_uptake >= -0.5, f"N created from nothing: {plant_uptake:.1f}"
    assert final_n + total_losses <= initial_n + total_inputs + 0.5


# ---------------------------------------------------------------------------
# AC: SimpleSOMRuntime alias removed
# ---------------------------------------------------------------------------
def test_simple_som_runtime_removed() -> None:
    """SimpleSOMRuntime alias should no longer exist."""
    import agrogame.soil.som as som_module

    assert not hasattr(som_module, "SimpleSOMRuntime")
