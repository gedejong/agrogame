"""Smoke test that the dashboard module imports without side effects.

This prevents regressions where optional deps or top-level code break imports.
"""

import importlib
import sys

import pytest


@pytest.mark.skipif(sys.version_info < (3, 10), reason="dashboard targets Python 3.10+")
def test_import_dashboard_module() -> None:
    # Skip if optional dashboard extras are not available in this environment
    pytest.importorskip("plotly")
    pytest.importorskip("streamlit")
    mod = importlib.import_module("agrogame.dashboard.app")
    assert hasattr(mod, "main")
