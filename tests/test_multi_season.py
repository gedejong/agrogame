"""Tests for multi-season simulation with soil state persistence (AGRO-99)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import (
    FullSimulationOrchestrator,
    SoilSnapshot,
)
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _load_presets() -> tuple:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    climate = climates.climates["netherlands_temperate"]
    return crops, climate, profile


def _run_season(
    orch: FullSimulationOrchestrator,
    climate_name: str = "netherlands_temperate",
    start: date | None = None,
    days: int = 150,
    seed: int = 42,
) -> float:
    """Run one season and return final biomass."""
    if start is None:
        start = date(2024, 4, 1)
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates[climate_name]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, start)
    for rec in series.records:
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
    return orch.canopy.state.biomass_g_m2


# ---------------------------------------------------------------------------
# AC1: reset_crop preserves soil, resets plant
# ---------------------------------------------------------------------------
class TestResetCrop:
    def test_plant_state_resets(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        assert orch.canopy.state.biomass_g_m2 > 0
        assert orch.canopy.state.lai > 0

        orch.reset_crop(crops.crops["spring_wheat"])
        assert orch.canopy.state.biomass_g_m2 == 0.0
        assert orch.canopy.state.lai == 0.0
        assert orch.phenology.state.accumulated_gdd == 0.0

    def test_soil_n_preserved(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        n_before = orch.n_state.total_nitrogen_kg_ha()

        orch.reset_crop(crops.crops["spring_wheat"])
        n_after = orch.n_state.total_nitrogen_kg_ha()
        assert n_after == pytest.approx(n_before, rel=1e-6)

    def test_soil_water_preserved(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        theta_before = list(orch.water_state.theta)

        orch.reset_crop(crops.crops["spring_wheat"])
        assert orch.water_state.theta == theta_before

    def test_soil_p_preserved(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        p_before = orch.p_state.total_phosphorus_kg_ha()

        orch.reset_crop(crops.crops["spring_wheat"])
        p_after = orch.p_state.total_phosphorus_kg_ha()
        assert p_after == pytest.approx(p_before, rel=1e-6)

    def test_microbe_state_preserved(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        microbe_c_before = [ly.c_kg_ha for ly in orch.microbes.state.layers]

        orch.reset_crop(crops.crops["spring_wheat"])
        microbe_c_after = [ly.c_kg_ha for ly in orch.microbes.state.layers]
        assert microbe_c_after == microbe_c_before

    def test_soil_ph_preserved(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        ph_before = list(orch.chem.ph_by_layer)

        orch.reset_crop(crops.crops["spring_wheat"])
        ph_after = list(orch.chem.ph_by_layer)
        assert ph_after == ph_before

    def test_simulation_works_after_reset(self) -> None:
        """Second season runs without errors after reset_crop."""
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=100)
        orch.reset_crop(crops.crops["spring_wheat"])
        biomass = _run_season(orch, start=date(2025, 4, 1), days=100, seed=99)
        assert biomass > 0


# ---------------------------------------------------------------------------
# AC2: harvest returns soil snapshot
# ---------------------------------------------------------------------------
class TestHarvest:
    def test_returns_snapshot(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        snap = orch.harvest()
        assert isinstance(snap, SoilSnapshot)
        assert len(snap.water_theta) == len(profile.layers)
        assert len(snap.n_nh4) == len(profile.layers)

    def test_snapshot_matches_state(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        snap = orch.harvest()
        assert snap.water_theta == orch.water_state.theta
        assert snap.n_no3 == orch.n_state.no3
        assert snap.p_available == orch.p_state.available_p


# ---------------------------------------------------------------------------
# AC3: 2-season maize→wheat different from standalone wheat (N depletion)
# ---------------------------------------------------------------------------
class TestTwoSeasonNDepletion:
    def test_maize_then_wheat_differs_from_standalone_wheat(self) -> None:
        """Wheat after maize should differ from standalone wheat due to
        soil N depletion during the first maize season.

        Source: crop rotation literature — preceding crop affects N
        availability for following crop (Angus et al. 2015).
        """
        crops, climate, profile = _load_presets()

        # Standalone wheat
        orch_solo = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["spring_wheat"],
            latitude_deg=climate.latitude_deg,
        )
        solo_wheat_biomass = _run_season(
            orch_solo, start=date(2025, 4, 1), days=150, seed=99
        )

        # 2-season: maize first, then wheat
        orch_rotation = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["maize"],
            latitude_deg=climate.latitude_deg,
        )
        _run_season(orch_rotation, start=date(2024, 4, 1), days=150, seed=42)
        orch_rotation.reset_crop(crops.crops["spring_wheat"])
        rotation_wheat_biomass = _run_season(
            orch_rotation, start=date(2025, 4, 1), days=150, seed=99
        )

        # Yields should differ — N depletion from maize affects wheat
        assert rotation_wheat_biomass != pytest.approx(solo_wheat_biomass, rel=0.01)


# ---------------------------------------------------------------------------
# AC4: Soil water carries over between seasons
# ---------------------------------------------------------------------------
class TestWaterCarryover:
    def test_dry_end_means_dry_start(self) -> None:
        """Soil water at end of season 1 should equal start of season 2."""
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["maize"],
            latitude_deg=climate.latitude_deg,
        )
        _run_season(orch, days=150)
        theta_end_season1 = list(orch.water_state.theta)

        # Not at field capacity (simulation consumed water)
        fc = [layer.field_capacity for layer in profile.layers]
        assert theta_end_season1 != fc

        orch.reset_crop(crops.crops["spring_wheat"])
        theta_start_season2 = list(orch.water_state.theta)
        assert theta_start_season2 == theta_end_season1


# ---------------------------------------------------------------------------
# AC5: Serialization round-trip
# ---------------------------------------------------------------------------
class TestSoilSerialization:
    def test_to_dict_from_dict_roundtrip(self) -> None:
        snap = SoilSnapshot(
            water_theta=[0.3, 0.25, 0.2],
            n_nh4=[5.0, 3.0, 1.0],
            n_no3=[10.0, 8.0, 4.0],
            n_organic=[100.0, 80.0, 50.0],
            p_available=[15.0, 12.0, 8.0],
            p_fixed=[2.0, 1.5, 1.0],
            p_organic=[30.0, 25.0, 15.0],
            microbe_c=[200.0, 180.0, 150.0],
            microbe_n=[25.0, 22.0, 18.0],
            microbe_fungal_fraction=[0.4, 0.35, 0.3],
            ph=[6.7, 6.6, 6.5],
        )
        d = snap.to_dict()
        restored = SoilSnapshot.from_dict(d)
        assert restored == snap

    def test_json_roundtrip(self) -> None:
        """Snapshot survives JSON serialization (game save/load)."""
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["maize"],
            latitude_deg=climate.latitude_deg,
        )
        _run_season(orch, days=50)
        snap = orch.harvest()

        json_str = json.dumps(snap.to_dict())
        restored = SoilSnapshot.from_dict(json.loads(json_str))
        assert restored == snap

    def test_restore_soil_from_snapshot(self) -> None:
        """Orchestrator can restore soil state from a snapshot."""
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["maize"],
            latitude_deg=climate.latitude_deg,
        )
        _run_season(orch, days=100)
        snap = orch.snapshot_soil()

        # Create fresh orchestrator and restore
        orch2 = FullSimulationOrchestrator(
            profile,
            crop=crops.crops["spring_wheat"],
            latitude_deg=climate.latitude_deg,
        )
        orch2.restore_soil(snap)
        assert orch2.water_state.theta == snap.water_theta
        assert orch2.n_state.no3 == snap.n_no3
        assert orch2.p_state.available_p == snap.p_available


# ---------------------------------------------------------------------------
# EventBus.clear()
# ---------------------------------------------------------------------------
class TestEventBusClear:
    def test_clear_removes_handlers(self) -> None:
        bus = EventBus()

        class DummyEvent:
            pass

        calls: list[str] = []
        bus.subscribe(DummyEvent, lambda e: calls.append("handled"))
        bus.emit(DummyEvent())
        assert len(calls) == 1

        bus.clear()
        bus.emit(DummyEvent())
        assert len(calls) == 1  # no new calls after clear
