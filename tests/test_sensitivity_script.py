"""Smoke test for sensitivity_analysis.py script.

Runs a minimal Morris analysis (N=2) to verify the script imports,
runs the model, and produces output. Skipped if SALib is not installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Guard: skip if SALib not available
try:
    import SALib  # noqa: F401
except ImportError:
    pytest.skip("SALib not installed", allow_module_level=True)

# Add scripts to path for import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


def test_sensitivity_script_imports() -> None:
    """The script module should import without error."""
    import sensitivity_analysis  # noqa: F811

    assert hasattr(sensitivity_analysis, "run_morris")
    assert hasattr(sensitivity_analysis, "PARAM_DEFS")
    assert len(sensitivity_analysis.PARAM_DEFS) >= 15


def test_salib_problem_definition() -> None:
    """Problem definition should match PARAM_DEFS count."""
    from sensitivity_analysis import _build_salib_problem, PARAM_DEFS

    problem = _build_salib_problem()
    assert problem["num_vars"] == len(PARAM_DEFS)
    assert len(problem["names"]) == len(PARAM_DEFS)
    assert all(lo < hi for lo, hi in problem["bounds"])


def test_single_model_run() -> None:
    """A single model run should return 4 numeric outputs."""
    import numpy as np
    from datetime import date
    from sensitivity_analysis import PARAM_DEFS, run_model

    defaults = np.array([p["default"] for p in PARAM_DEFS])
    result = run_model(
        defaults, "maize", "netherlands_temperate", date(2024, 4, 1), 150
    )
    assert len(result) == 4
    assert all(isinstance(v, float) for v in result)
    assert result[0] > 0  # biomass
    assert result[1] > 0  # peak LAI


def test_morris_minimal_run(tmp_path: Path) -> None:
    """Morris with N=2 should produce results without error."""
    from datetime import date
    from sensitivity_analysis import run_morris, write_results_csv, top_n_parameters

    results = run_morris(
        "maize", "netherlands_temperate", date(2024, 4, 1), 150, trajectories=2
    )
    assert "final_biomass_g_m2" in results
    assert len(results["final_biomass_g_m2"]["mu_star"]) == len(
        results["final_biomass_g_m2"]["names"]
    )

    csv_path = write_results_csv(results, "test", tmp_path)
    assert csv_path.exists()

    top = top_n_parameters(results, n=3)
    assert len(top["final_biomass_g_m2"]) == 3
