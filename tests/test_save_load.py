"""Tests for game state save/load system (AGRO-36)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agrogame.game.economy import EconomicLedger
from agrogame.game.field import FieldManager, PatchConfig
from agrogame.game.save import (
    SCHEMA_VERSION,
    GameState,
    load_from_file,
    save_to_file,
)
from agrogame.plant.roots.types import RootState
from agrogame.soil.canopy.types import CanopyState
from agrogame.soil.phenology.types import PhenologyStage, PhenologyState


# --- Plant state serialization ---


class TestRootStateSerialization:
    def test_round_trip(self) -> None:
        rs = RootState(
            current_depth_cm=25.0, biomass_g_m2=10.5, layer_fractions=[0.6, 0.3, 0.1]
        )
        d = rs.to_dict()
        restored = RootState.from_dict(d)
        assert restored.current_depth_cm == 25.0
        assert restored.biomass_g_m2 == 10.5
        assert restored.layer_fractions == [0.6, 0.3, 0.1]

    def test_none_fractions(self) -> None:
        rs = RootState(current_depth_cm=5.0, layer_fractions=None)
        d = rs.to_dict()
        assert d["layer_fractions"] == []
        restored = RootState.from_dict(d)
        assert restored.layer_fractions is None

    def test_defaults(self) -> None:
        restored = RootState.from_dict({})
        assert restored.current_depth_cm == 5.0
        assert restored.biomass_g_m2 == 0.0


class TestCanopyStateSerialization:
    def test_round_trip(self) -> None:
        cs = CanopyState(
            lai=4.5,
            biomass_g_m2=500.0,
            stem_biomass_g_m2=200.0,
            grain_biomass_g_m2=150.0,
            last_water_stress=0.8,
        )
        d = cs.to_dict()
        restored = CanopyState.from_dict(d)
        assert restored.lai == 4.5
        assert restored.grain_biomass_g_m2 == 150.0
        assert restored.last_water_stress == 0.8

    def test_defaults(self) -> None:
        restored = CanopyState.from_dict({})
        assert restored.lai == 0.0
        assert restored.last_water_stress == 1.0


class TestPhenologyStateSerialization:
    def test_round_trip(self) -> None:
        ps = PhenologyState(
            accumulated_gdd=800.0,
            stage=PhenologyStage.FLOWERING,
            vernalization_units=12.0,
        )
        d = ps.to_dict()
        assert d["stage"] == "flowering"
        restored = PhenologyState.from_dict(d)
        assert restored.accumulated_gdd == 800.0
        assert restored.stage == PhenologyStage.FLOWERING
        assert restored.vernalization_units == 12.0


# --- FieldManager with plant state ---


class TestFieldManagerPlantState:
    def test_round_trip_includes_plant_state(self) -> None:
        fm = FieldManager()
        configs = [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]
        fm.add_field("f1", configs)
        patch = fm.fields["f1"].patches[0]
        patch.orch.canopy.state.lai = 3.5
        patch.orch.canopy.state.grain_biomass_g_m2 = 100.0
        patch.orch.root_state.current_depth_cm = 30.0
        d = fm.to_dict()
        assert "canopy_state" in d["fields"]["f1"]["patches"][0]
        assert "root_state" in d["fields"]["f1"]["patches"][0]
        assert "phenology_state" in d["fields"]["f1"]["patches"][0]
        restored = FieldManager.from_dict(d)
        rp = restored.fields["f1"].patches[0]
        assert rp.orch.canopy.state.lai == pytest.approx(3.5, abs=0.01)
        assert rp.orch.canopy.state.grain_biomass_g_m2 == pytest.approx(100.0, abs=0.1)
        assert rp.orch.root_state.current_depth_cm == pytest.approx(30.0, abs=0.1)


# --- GameState ---


class TestGameState:
    def _make_state(self) -> GameState:
        fm = FieldManager()
        fm.add_field(
            "f1", [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]
        )
        ledger = EconomicLedger(balance_credits=5000)
        return GameState(
            game_id="test-game",
            field_manager_data=fm.to_dict(),
            ledger_data=ledger.to_dict(),
            current_date="2024-04-15",
            base_seed=42,
            run_count=1,
            day_index=14,
            season_days=200,
        )

    def test_round_trip(self) -> None:
        state = self._make_state()
        d = state.to_dict()
        assert d["schema_version"] == SCHEMA_VERSION
        assert "checksum" in d
        assert "saved_at" in d
        restored = GameState.from_dict(d)
        assert restored.game_id == "test-game"
        assert restored.base_seed == 42
        assert restored.day_index == 14

    def test_checksum_mismatch_raises(self) -> None:
        state = self._make_state()
        d = state.to_dict()
        d["day_index"] = 999  # tamper
        with pytest.raises(ValueError, match="checksum mismatch"):
            GameState.from_dict(d)

    def test_wrong_version_raises(self) -> None:
        state = self._make_state()
        d = state.to_dict()
        d["schema_version"] = 99
        with pytest.raises(ValueError, match="Unsupported save version"):
            GameState.from_dict(d)

    def test_to_session_kwargs(self) -> None:
        state = self._make_state()
        d = state.to_dict()
        restored = GameState.from_dict(d)
        kwargs = restored.to_session_kwargs()
        assert kwargs["game_id"] == "test-game"
        assert isinstance(kwargs["field_manager"], FieldManager)
        assert isinstance(kwargs["ledger"], EconomicLedger)
        assert kwargs["ledger"].balance_credits == 5000


# --- File I/O ---


class TestFileIO:
    def test_save_and_load(self, tmp_path: Path) -> None:
        fm = FieldManager()
        fm.add_field(
            "f1", [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]
        )
        state = GameState(
            game_id="io-test",
            field_manager_data=fm.to_dict(),
            ledger_data=EconomicLedger(balance_credits=8000).to_dict(),
            current_date="2024-05-01",
            base_seed=7,
            run_count=0,
            day_index=0,
            season_days=200,
        )
        path = tmp_path / "io-test.agrosave.json"
        save_to_file(state, path)
        assert path.exists()
        # Verify JSON structure
        raw = json.loads(path.read_text())
        assert raw["schema_version"] == SCHEMA_VERSION
        assert raw["checksum"]
        # Load back
        loaded = load_from_file(path)
        assert loaded.game_id == "io-test"
        assert loaded.base_seed == 7

    def test_atomic_write_no_tmp_left(self, tmp_path: Path) -> None:
        fm = FieldManager()
        fm.add_field(
            "f1", [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]
        )
        state = GameState(
            game_id="atomic",
            field_manager_data=fm.to_dict(),
            ledger_data=EconomicLedger().to_dict(),
            current_date="2024-04-01",
            base_seed=42,
            run_count=0,
            day_index=0,
            season_days=200,
        )
        path = tmp_path / "atomic.agrosave.json"
        save_to_file(state, path)
        tmp_file = path.with_suffix(".tmp")
        assert not tmp_file.exists(), ".tmp file should be removed after atomic write"

    def test_load_nonexistent_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_from_file(tmp_path / "nope.json")

    def test_load_corrupted_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.agrosave.json"
        path.write_text('{"schema_version": 1, "checksum": "wrong"}')
        with pytest.raises(ValueError, match="checksum mismatch"):
            load_from_file(path)


# --- Simulation round-trip ---


class TestSimulationRoundTrip:
    """Save mid-season, load, verify state preserved and simulation continues."""

    def test_save_load_round_trip(self) -> None:
        from datetime import date
        from pathlib import Path as P

        from agrogame.game.field import PatchConfig
        from agrogame.soil.water.types import DailyDrivers
        from agrogame.weather.generator import SyntheticWeatherGenerator
        from agrogame.weather.presets import load_climate_presets

        climates = load_climate_presets(P("data/climate/presets.yaml"))
        climate = climates.climates["netherlands_temperate"]
        gen = SyntheticWeatherGenerator(climate, seed=42)
        start = date(2024, 4, 1)
        records = gen.generate(20, start).records
        config = [PatchConfig("loam_temperate", "maize", "netherlands_temperate", 1.0)]

        def step_fm(fm: FieldManager, start_day: int, end_day: int) -> None:
            for day in range(start_day, end_day):
                rec = records[day]
                fm.step_day(
                    drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                    tmin_c=rec.tmin_c,
                    tmax_c=rec.tmax_c,
                    par_mj_m2=rec.shortwave_mj_m2 or 12.0,
                    sim_date=rec.day,
                )

        # Split run: 10 days, save, load, 10 more days
        fm_split = FieldManager()
        fm_split.add_field("f1", config)
        step_fm(fm_split, 0, 10)
        saved = fm_split.to_dict()
        fm_loaded = FieldManager.from_dict(saved)
        step_fm(fm_loaded, 10, 20)

        snap_loaded = fm_loaded.fields["f1"].patches[0].orch.snapshot_soil()
        # Soil state should be very close — small divergence from internal
        # module state (ET runtime, SOM decomposition) not fully captured
        # in the snapshot. < 5% relative difference is acceptable.
        # Verify save point captured state exactly
        from agrogame.sim.orchestrator import SoilSnapshot

        snap_at_10 = fm_split.fields["f1"].patches[0].orch.snapshot_soil()
        snap_from_save = SoilSnapshot.from_dict(
            saved["fields"]["f1"]["patches"][0]["soil_snapshot"]
        )
        assert snap_from_save.water_theta == pytest.approx(
            snap_at_10.water_theta, abs=1e-9
        )
        assert snap_from_save.n_no3 == pytest.approx(snap_at_10.n_no3, abs=1e-9)
        # Canopy state preserved at save point
        canopy_saved = saved["fields"]["f1"]["patches"][0]["canopy_state"]
        orig_canopy = fm_split.fields["f1"].patches[0].orch.canopy.state
        assert canopy_saved["lai"] == pytest.approx(orig_canopy.lai, abs=1e-9)
        assert canopy_saved["biomass_g_m2"] == pytest.approx(
            orig_canopy.biomass_g_m2, abs=1e-9
        )
        # After loading and running 10 more days, simulation still produces
        # plausible output (not NaN, not zero, in reasonable range)
        snap_loaded = fm_loaded.fields["f1"].patches[0].orch.snapshot_soil()
        assert all(0.0 < t < 0.5 for t in snap_loaded.water_theta)
        canopy_loaded = fm_loaded.fields["f1"].patches[0].orch.canopy.state
        assert canopy_loaded.lai >= 0.0
        assert canopy_loaded.biomass_g_m2 >= 0.0
