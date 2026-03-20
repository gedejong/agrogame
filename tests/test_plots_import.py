"""Smoke tests that agrogame.plots.* modules import without side effects."""

from __future__ import annotations

import importlib

import pytest


_PLOTS_MODULES = [
    ("agrogame.plots.et", "plot_et_timeseries"),
    ("agrogame.plots.events", "plot_timeline"),
    ("agrogame.plots.full_integration", "main"),
    ("agrogame.plots.interception", "plot_interception_isolation"),
    ("agrogame.plots.microbes", "plot_microbes_timeseries"),
    ("agrogame.plots.nutrients", "plot_nitrogen_timeseries"),
    ("agrogame.plots.phenology_roots", "simulate_phenology_canopy"),
    ("agrogame.plots.roots_compare", "plot_roots_compare"),
    ("agrogame.plots.utils", "moving_average"),
    ("agrogame.plots.water", "plot_water_timeseries"),
]


@pytest.mark.parametrize("module_path,public_name", _PLOTS_MODULES)
def test_import_plots_module(module_path: str, public_name: str) -> None:
    pytest.importorskip("matplotlib")
    mod = importlib.import_module(module_path)
    assert hasattr(mod, public_name)
