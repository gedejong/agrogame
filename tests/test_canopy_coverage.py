"""Tests covering missing lines in agrogame/soil/canopy/module.py."""

from __future__ import annotations

import pytest

from agrogame.events import EventBus
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.soil.canopy.events import Harvested, LAIUpdated


def _default_params() -> CanopyParams:
    return CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.01,
    )


# ---------------------------------------------------------------------------
# _on_harvest (lines 86-91)
# ---------------------------------------------------------------------------


def test_harvest_reduces_lai_and_biomass() -> None:
    """Cover lines 86-91: _on_harvest handler."""
    bus = EventBus()
    canopy = CanopyModule(_default_params(), event_bus=bus)
    canopy.state.lai = 4.0
    canopy.state.biomass_g_m2 = 200.0
    captured = []
    bus.subscribe(LAIUpdated, lambda e: captured.append(e))
    bus.emit(Harvested(fraction_remaining=0.1))
    assert canopy.state.lai == pytest.approx(0.4, abs=1e-6)
    assert canopy.state.biomass_g_m2 == pytest.approx(20.0, abs=1e-6)
    assert len(captured) == 1


# ---------------------------------------------------------------------------
# daily_step_with_transpiration (lines 169-170)
# ---------------------------------------------------------------------------


def test_daily_step_with_transpiration() -> None:
    """Cover lines 169-170: daily_step_with_transpiration."""
    canopy = CanopyModule(_default_params())
    canopy.state.lai = 3.0
    canopy.state.biomass_g_m2 = 100.0
    result = canopy.daily_step_with_transpiration(
        incident_par_mj_m2=10.0,
        temp_factor=1.0,
        actual_transpiration_mm=2.0,
        potential_transpiration_mm=4.0,
        n_stress=1.0,
    )
    assert result.intercepted_par_mj_m2 > 0.0
    assert result.biomass_increment_g_m2 > 0.0
