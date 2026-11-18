from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema.exceptions import ValidationError

from agrogame.weather.presets import (
    ClimatePreset,
    load_climate_presets,
    _load_climate_presets_cached,
)


def test_load_three_presets() -> None:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    assert len(lib.climates) == 3
    assert "netherlands_temperate" in lib.climates
    assert "kenya_highlands" in lib.climates
    assert "sahel_arid" in lib.climates


def test_preset_fields_populated() -> None:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    nl = lib.climates["netherlands_temperate"]
    assert isinstance(nl, ClimatePreset)
    assert nl.latitude_deg == 52.0
    assert nl.annual_mean_tmin_c < nl.annual_mean_tmax_c
    assert 0.0 <= nl.heatwave_probability <= 1.0


def test_sahel_hotter_than_netherlands() -> None:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    nl = lib.climates["netherlands_temperate"]
    sahel = lib.climates["sahel_arid"]
    assert sahel.annual_mean_tmax_c > nl.annual_mean_tmax_c


def test_missing_file_raises() -> None:
    _load_climate_presets_cached.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_climate_presets(Path("nonexistent.yaml"))


def test_caching_returns_same_object() -> None:
    _load_climate_presets_cached.cache_clear()
    p = Path("data/climate/presets.yaml")
    a = load_climate_presets(p)
    b = load_climate_presets(p)
    assert a is b


# --- Optional monthly normals: loader checks (#500 AC1) ----------------------


def _sahel_raw() -> dict[str, Any]:
    raw = yaml.safe_load(Path("data/climate/presets.yaml").read_text("utf-8"))
    return copy.deepcopy(raw["climates"]["sahel_arid"])


def _load_single(tmp_path: Path, preset: dict[str, Any]) -> ClimatePreset:
    path = tmp_path / "climate.yaml"
    path.write_text(yaml.safe_dump({"climates": {"x": preset}}), "utf-8")
    return load_climate_presets(path).climates["x"]


def test_sahel_monthly_normals_loaded_and_consistent() -> None:
    """The shipped arrays load, and each annual mean is its array mean (2 dp)."""
    _load_climate_presets_cached.cache_clear()
    sahel = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "sahel_arid"
    ]
    assert len(sahel.monthly_mean_tmin_c) == 12
    assert len(sahel.monthly_mean_tmax_c) == 12
    assert len(sahel.monthly_mean_shortwave_mj_m2) == 12
    for values, annual in (
        (sahel.monthly_mean_tmin_c, sahel.annual_mean_tmin_c),
        (sahel.monthly_mean_tmax_c, sahel.annual_mean_tmax_c),
        (sahel.monthly_mean_shortwave_mj_m2, sahel.annual_mean_shortwave_mj_m2),
    ):
        assert round(sum(values) / 12.0, 2) == annual


def test_only_one_temperature_array_raises(tmp_path: Path) -> None:
    raw = _sahel_raw()
    del raw["monthly_mean_tmax_c"]
    with pytest.raises(ValueError, match="must be given together"):
        _load_single(tmp_path, raw)


def test_month_with_tmin_not_below_tmax_raises(tmp_path: Path) -> None:
    raw = _sahel_raw()
    raw["monthly_mean_tmin_c"], raw["monthly_mean_tmax_c"] = (
        raw["monthly_mean_tmax_c"],
        raw["monthly_mean_tmin_c"],
    )
    with pytest.raises(ValueError, match="month 1 has tmin"):
        _load_single(tmp_path, raw)


@pytest.mark.parametrize(
    "array_key",
    ["monthly_mean_tmin_c", "monthly_mean_tmax_c", "monthly_mean_shortwave_mj_m2"],
)
def test_array_mean_off_its_annual_field_raises(tmp_path: Path, array_key: str) -> None:
    """Shift every month by +0.1 and leave ``annual_mean_*`` alone (tol 0.05)."""
    raw = _sahel_raw()
    raw[array_key] = [v + 0.1 for v in raw[array_key]]
    with pytest.raises(ValueError, match=f"{array_key} averages"):
        _load_single(tmp_path, raw)


@pytest.mark.parametrize(
    ("array_key", "values"),
    [
        ("monthly_mean_tmin_c", [20.0] * 11),
        ("monthly_mean_shortwave_mj_m2", [-1.0] + [20.0] * 11),
    ],
)
def test_schema_rejects_bad_monthly_arrays(
    tmp_path: Path, array_key: str, values: list[float]
) -> None:
    raw = _sahel_raw()
    raw[array_key] = values
    with pytest.raises(ValidationError, match=array_key):
        _load_single(tmp_path, raw)


def test_direct_construction_checks_array_length() -> None:
    """The dataclass guards its own arrays, not only the YAML schema does."""
    with pytest.raises(ValueError, match="needs 12 values"):
        ClimatePreset(
            name="short",
            latitude_deg=0.0,
            longitude_deg=0.0,
            annual_mean_tmin_c=20.0,
            annual_mean_tmax_c=30.0,
            annual_temp_amplitude_c=0.0,
            annual_mean_precip_mm_day=1.0,
            annual_mean_rh_pct=50.0,
            annual_mean_wind_m_s=2.0,
            annual_mean_shortwave_mj_m2=20.0,
            monthly_mean_shortwave_mj_m2=[20.0] * 11,
        )
