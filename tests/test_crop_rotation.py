"""Tests for crop rotation with N credits and history tracking (AGRO-32)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets, _load_crop_presets_cached
from agrogame.sim.orchestrator import FullSimulationOrchestrator, SoilSnapshot
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _load_presets() -> tuple:
    _load_crop_presets_cached.cache_clear()
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
# AC: soybean preset exists with N fixation
# ---------------------------------------------------------------------------
class TestSoybeanPreset:
    def test_soybean_exists(self) -> None:
        crops, _, _ = _load_presets()
        assert "soybean" in crops.crops

    def test_soybean_has_n_fixation_credit(self) -> None:
        crops, _, _ = _load_presets()
        soy = crops.crops["soybean"]
        assert soy.n_fixation_credit_kg_ha == 60.0

    def test_non_legumes_have_zero_credit(self) -> None:
        crops, _, _ = _load_presets()
        assert crops.crops["maize"].n_fixation_credit_kg_ha == 0.0
        assert crops.crops["spring_wheat"].n_fixation_credit_kg_ha == 0.0


# ---------------------------------------------------------------------------
# AC: crop_history records correct sequence after 3 seasons
# ---------------------------------------------------------------------------
class TestCropHistory:
    def test_history_tracks_three_seasons(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        orch.harvest()
        orch.reset_crop(crops.crops["soybean"])

        _run_season(orch, start=date(2025, 4, 1), days=50, seed=99)
        orch.harvest()
        orch.reset_crop(crops.crops["spring_wheat"])

        _run_season(orch, start=date(2026, 4, 1), days=50, seed=77)
        orch.harvest()

        assert orch.crop_history == [
            "maize",
            "soybean",
            "spring_wheat",
        ]

    def test_history_empty_initially(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        assert orch.crop_history == []


# ---------------------------------------------------------------------------
# AC: N credit added to organic_n pool (not mineral N)
# ---------------------------------------------------------------------------
class TestNFixationCredit:
    def test_legume_harvest_adds_organic_n(self) -> None:
        """After soybean harvest, organic_n[0] should increase by 60 kg/ha.

        N fixation credit goes to organic N for slow release via
        mineralization (Peoples et al. 2009).
        """
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["soybean"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        organic_n_before = orch.n_state.organic_n[0]
        nh4_before = orch.n_state.nh4[0]
        no3_before = orch.n_state.no3[0]

        orch.harvest()

        # Organic N increased by fixation credit
        assert orch.n_state.organic_n[0] == pytest.approx(
            organic_n_before + 60.0, abs=0.01
        )
        # Mineral N unchanged by fixation (only organic pool)
        assert orch.n_state.nh4[0] == pytest.approx(nh4_before, abs=0.01)
        assert orch.n_state.no3[0] == pytest.approx(no3_before, abs=0.01)

    def test_non_legume_harvest_no_n_credit(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        organic_n_before = orch.n_state.organic_n[0]
        orch.harvest()
        assert orch.n_state.organic_n[0] == pytest.approx(organic_n_before, abs=0.01)


# ---------------------------------------------------------------------------
# AC: soybean→maize > maize→maize (N credit effect)
# ---------------------------------------------------------------------------
class TestRotationBenefit:
    def test_soybean_maize_outperforms_maize_maize(self) -> None:
        """Soybean→maize rotation should produce more maize biomass than
        maize→maize, due to N fixation credit from soybean.

        Source: Peoples et al. (2009) — legume N contributions to
        cropping systems. Plant and Soil, 311:1-18.
        """
        crops, climate, profile = _load_presets()

        def _deplete_n(orch: FullSimulationOrchestrator) -> None:
            """Zero out all N pools to make N credit from legume visible."""
            for i in range(len(orch.n_state.nh4)):
                orch.n_state.nh4[i] = 0.0
                orch.n_state.no3[i] = 0.0
                orch.n_state.organic_n[i] = 0.0

        # Rotation: soybean then maize (on N-depleted soil)
        orch_rot = FullSimulationOrchestrator(
            profile, crop=crops.crops["soybean"], latitude_deg=climate.latitude_deg
        )
        _deplete_n(orch_rot)
        _run_season(orch_rot, days=150)
        orch_rot.harvest()  # adds 60 kg/ha organic N from soybean
        orch_rot.reset_crop(crops.crops["maize"])
        rot_maize = _run_season(orch_rot, start=date(2025, 4, 1), days=150, seed=99)

        # Monoculture: maize then maize (on N-depleted soil)
        orch_mono = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _deplete_n(orch_mono)
        _run_season(orch_mono, days=150)
        orch_mono.harvest()  # no N credit from maize
        orch_mono.reset_crop(crops.crops["maize"])
        mono_maize = _run_season(orch_mono, start=date(2025, 4, 1), days=150, seed=99)

        assert rot_maize > mono_maize


# ---------------------------------------------------------------------------
# AC: SoilSnapshot includes crop_history for save/load
# ---------------------------------------------------------------------------
class TestSnapshotHistory:
    def test_snapshot_includes_history(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        snap = orch.harvest()
        assert snap.crop_history == ["maize"]

    def test_json_roundtrip_preserves_history(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["soybean"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        snap = orch.harvest()

        json_str = json.dumps(snap.to_dict())
        restored = SoilSnapshot.from_dict(json.loads(json_str))
        assert restored.crop_history == snap.crop_history

    def test_restore_preserves_history(self) -> None:
        crops, climate, profile = _load_presets()
        orch = FullSimulationOrchestrator(
            profile, crop=crops.crops["maize"], latitude_deg=climate.latitude_deg
        )
        _run_season(orch, days=50)
        snap = orch.harvest()

        orch2 = FullSimulationOrchestrator(
            profile, crop=crops.crops["soybean"], latitude_deg=climate.latitude_deg
        )
        orch2.restore_soil(snap)
        assert orch2.crop_history == ["maize"]
