"""Tests for FieldManager with patch support (AGRO-108)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from agrogame.game.field import (
    Field,
    FieldManager,
    PatchConfig,
)
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets


def _nl_drivers(days: int = 30, seed: int = 42) -> list[tuple]:
    """Generate NL weather records for testing."""
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    climate = climates.climates["netherlands_temperate"]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, date(2024, 4, 1))
    return [
        (
            DailyDrivers(rainfall_mm=r.precip_mm or 0.0),
            r.tmin_c,
            r.tmax_c,
            r.shortwave_mj_m2 or 12.0,
            r.day,
        )
        for r in series.records
    ]


def _two_patch_configs() -> list[PatchConfig]:
    return [
        PatchConfig("loam_temperate", "maize", "netherlands_temperate", 0.6),
        PatchConfig("loam_temperate", "spring_wheat", "netherlands_temperate", 0.4),
    ]


# ---------------------------------------------------------------------------
# PatchConfig validation
# ---------------------------------------------------------------------------
class TestPatchConfig:
    def test_fractions_must_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            Field(
                "bad",
                [
                    PatchConfig(
                        "loam_temperate", "maize", "netherlands_temperate", 0.3
                    ),
                    PatchConfig(
                        "loam_temperate", "maize", "netherlands_temperate", 0.3
                    ),
                ],
            )

    def test_valid_fractions(self) -> None:
        f = Field("ok", _two_patch_configs())
        assert len(f.patches) == 2


# ---------------------------------------------------------------------------
# AC: 3 fields x 2 patches runs 150 days
# ---------------------------------------------------------------------------
def test_multi_field_multi_patch_150_days() -> None:
    mgr = FieldManager()
    for i in range(3):
        mgr.add_field(f"field_{i}", _two_patch_configs())

    records = _nl_drivers(150)
    for drivers, tmin, tmax, par, sim_date in records:
        mgr.step_day(
            drivers=drivers,
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=par,
            sim_date=sim_date,
        )

    # All fields should have produced biomass
    for fid in mgr.fields:
        results = mgr.harvest_field(fid)
        assert len(results) == 2
        for r in results:
            assert r.grain_g_m2 >= 0


# ---------------------------------------------------------------------------
# AC: patch-level action affects only targeted patch
# ---------------------------------------------------------------------------
def test_patch_action_targets_only_one_patch() -> None:
    mgr = FieldManager()
    mgr.add_field("f1", _two_patch_configs())

    # Get initial NH4 for both patches
    p0_nh4_before = mgr.fields["f1"].patches[0].orch.n_state.nh4[0]
    p1_nh4_before = mgr.fields["f1"].patches[1].orch.n_state.nh4[0]

    # Apply fertilizer only to patch 0
    mgr.apply_patch_action("f1", 0, "fertilize", type="urea", amount_kg_ha=100.0)

    # Patch 0 changed, patch 1 unchanged
    assert mgr.fields["f1"].patches[0].orch.n_state.nh4[0] > p0_nh4_before
    assert mgr.fields["f1"].patches[1].orch.n_state.nh4[0] == p1_nh4_before


# ---------------------------------------------------------------------------
# AC: serialization round-trip
# ---------------------------------------------------------------------------
def test_serialization_roundtrip() -> None:
    mgr = FieldManager()
    mgr.add_field("f1", _two_patch_configs())

    # Run a few days to change state
    records = _nl_drivers(10)
    for drivers, tmin, tmax, par, sim_date in records:
        mgr.step_day(
            drivers=drivers, tmin_c=tmin, tmax_c=tmax, par_mj_m2=par, sim_date=sim_date
        )

    d = mgr.to_dict()
    json_str = json.dumps(d)
    restored = FieldManager.from_dict(json.loads(json_str))

    assert "f1" in restored.fields
    assert len(restored.fields["f1"].patches) == 2
    # Soil state should match
    orig_theta = mgr.fields["f1"].patches[0].orch.water_state.theta
    rest_theta = restored.fields["f1"].patches[0].orch.water_state.theta
    assert orig_theta == pytest.approx(rest_theta, abs=0.001)


# ---------------------------------------------------------------------------
# AC: harvest returns per-patch results
# ---------------------------------------------------------------------------
def test_harvest_returns_per_patch_results() -> None:
    mgr = FieldManager()
    mgr.add_field("f1", _two_patch_configs())

    records = _nl_drivers(50)
    for drivers, tmin, tmax, par, sim_date in records:
        mgr.step_day(
            drivers=drivers, tmin_c=tmin, tmax_c=tmax, par_mj_m2=par, sim_date=sim_date
        )

    results = mgr.harvest_field("f1")
    assert len(results) == 2
    assert results[0].patch_idx == 0
    assert results[1].patch_idx == 1
    assert results[0].crop_key == "maize"
    assert results[1].crop_key == "spring_wheat"
    assert isinstance(results[0].soil_snapshot, type(results[1].soil_snapshot))


# ---------------------------------------------------------------------------
# AC: field-level irrigation distributes by area fraction
# ---------------------------------------------------------------------------
def test_field_irrigation_distributes() -> None:
    f = Field("f1", _two_patch_configs())
    # Dry out both patches
    for p in f.patches:
        p.orch.water_state.theta[0] = p.orch.profile.layers[0].wilting_point
    theta_before = [p.orch.water_state.theta[0] for p in f.patches]

    f.apply_irrigation(50.0)  # 50mm total, split 60/40
    theta_after = [p.orch.water_state.theta[0] for p in f.patches]
    # Both should increase
    assert theta_after[0] > theta_before[0]
    assert theta_after[1] > theta_before[1]


# ---------------------------------------------------------------------------
# AC: add/remove fields
# ---------------------------------------------------------------------------
class TestFieldManagement:
    def test_add_field(self) -> None:
        mgr = FieldManager()
        mgr.add_field("f1", _two_patch_configs())
        assert "f1" in mgr.fields

    def test_duplicate_field_raises(self) -> None:
        mgr = FieldManager()
        mgr.add_field("f1", _two_patch_configs())
        with pytest.raises(ValueError, match="already exists"):
            mgr.add_field("f1", _two_patch_configs())

    def test_remove_field(self) -> None:
        mgr = FieldManager()
        mgr.add_field("f1", _two_patch_configs())
        mgr.remove_field("f1")
        assert "f1" not in mgr.fields

    def test_remove_nonexistent_raises(self) -> None:
        mgr = FieldManager()
        with pytest.raises(KeyError):
            mgr.remove_field("nope")


# ---------------------------------------------------------------------------
# AC: memory < 300MB for 30 orchestrators
# ---------------------------------------------------------------------------
def test_memory_30_orchestrators() -> None:
    """10 fields x 3 patches = 30 orchestrators should use < 300MB."""
    import tracemalloc

    tracemalloc.start()
    mgr = FieldManager()
    configs = [
        PatchConfig("loam_temperate", "maize", "netherlands_temperate", 0.5),
        PatchConfig("loam_temperate", "spring_wheat", "netherlands_temperate", 0.3),
        PatchConfig("loam_temperate", "sorghum", "netherlands_temperate", 0.2),
    ]
    for i in range(10):
        mgr.add_field(f"field_{i}", configs)

    _, peak_mb = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    peak_mb_val = peak_mb / (1024 * 1024)
    assert peak_mb_val < 300, f"Peak memory {peak_mb_val:.0f} MB exceeds 300 MB"
