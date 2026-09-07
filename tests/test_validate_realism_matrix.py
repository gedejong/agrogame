"""Smoke tests for ``scripts/validate_realism_matrix.py``.

The harness is a script rather than a package module, so it is loaded from
its file path. The tests cover the three layers a change to the harness can
break: matrix construction, a short season through ``run_one`` and the
grading of season scalars against a check band.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "validate_realism_matrix.py"


@pytest.fixture(scope="module")
def harness() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_realism_matrix", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Dataclass creation resolves postponed annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_matrix_is_the_crop_soil_climate_product_plus_stress_subset(
    harness: ModuleType,
) -> None:
    specs = harness.build_matrix(
        harness.ALL_CROPS,
        harness.ALL_SOILS,
        harness.ALL_CLIMATES,
        harness.STRESS_SCENARIOS,
        [harness.DEFAULT_SEED],
        True,
    )
    n_normal = (
        len(harness.ALL_CROPS) * len(harness.ALL_SOILS) * len(harness.ALL_CLIMATES)
    )
    n_stress = (
        len(harness.STRESS_SCENARIOS)
        * len(harness.STRESS_CROPS)
        * len(harness.STRESS_SOILS)
        * len(harness.ALL_CLIMATES)
    )
    assert len(specs) == n_normal + n_stress == 270
    assert len({s.run_id for s in specs}) == len(specs)
    assert sum(1 for s in specs if s.scenario == "normal") == n_normal


def test_list_option_prints_the_matrix_summary(
    harness: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert harness.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "270 runs (189 normal, 81 stress)" in out
    assert "maize__loam_temperate__kenya_highlands__normal__s42" in out


def test_short_season_completes_and_closes_the_water_balance(
    harness: ModuleType,
) -> None:
    libs = harness.load_libraries()
    spec = harness.make_spec(
        "maize",
        "loam_temperate",
        harness.KENYA,
        "normal",
        harness.DEFAULT_SEED,
        days=10,
    )
    result = harness.run_one(spec, libs)
    assert result.status == "ok", result.error
    assert len(result.daily) == 10
    assert abs(result.scalars["water_residual_mm"]) < 0.5
    assert result.scalars["nan_count"] == 0


def test_check_band_grades_scalars(harness: ModuleType) -> None:
    check = harness.Check("unit", "x", warn=(0.0, 10.0), fail=(-5.0, 20.0))
    scalars = {"run_id": "unit__run", "x": 5.0}
    assert harness.evaluate_check(check, scalars) is None
    warn = harness.evaluate_check(check, {**scalars, "x": 15.0})
    assert warn is not None and warn.severity == "WARN"
    fail = harness.evaluate_check(check, {**scalars, "x": 25.0})
    assert fail is not None and fail.severity == "FAIL"
    assert harness.evaluate_check(check, {**scalars, "x": math.nan}) is None
    assert harness.evaluate_check(check, {"run_id": "unit__run"}) is None
    assert harness.build_checks()
