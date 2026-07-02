"""Parameterized N/P rate constants (#320).

Verifies that the process-rate scalars now live in frozen ``*Params``
dataclasses, that defaults reproduce the historical inline values, that custom
params flow through to the cycle outputs, and that the clay-modulated rates
(denitrification, P fixation) respond to soil texture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from agrogame.events import EventBus
from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.nitrogen import NitrogenCycle, NitrogenRateParams, SoilNitrogenState
from agrogame.soil.phosphorus import (
    PhosphorusCycle,
    PhosphorusRateParams,
    SoilPhosphorusState,
)


def _profile(texture: str, clay_pct: float | None = None) -> SoilProfile:
    """Three-layer profile of a single texture (>=100 cm total depth)."""
    layers = [
        SoilLayer(
            depth_cm=40,
            texture=texture,
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=3.0,
            clay_pct=clay_pct,
            initial_no3_kg_ha=30.0,
            initial_nh4_kg_ha=10.0,
            initial_p_kg_ha=20.0,
        ),
        SoilLayer(
            depth_cm=30,
            texture=texture,
            field_capacity=0.28,
            wilting_point=0.11,
            saturation=0.42,
            bulk_density_g_cm3=1.35,
            ksat_mm_per_hour=18,
            organic_matter_pct=2.0,
            clay_pct=clay_pct,
            initial_no3_kg_ha=20.0,
            initial_nh4_kg_ha=5.0,
            initial_p_kg_ha=10.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture=texture,
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=1.5,
            clay_pct=clay_pct,
            initial_no3_kg_ha=10.0,
            initial_nh4_kg_ha=2.0,
            initial_p_kg_ha=5.0,
        ),
    ]
    return SoilProfile(name=f"{texture}_test", layers=layers)


def _saturate(water: SoilWaterState, profile: SoilProfile) -> None:
    """Push every layer to saturation so denitrification is active."""
    for i, layer in enumerate(profile.layers):
        water.theta[i] = layer.saturation


# --- Defaults reproduce historical inline constants (AC1/AC2) -------------


def test_nitrogen_defaults_match_historical_constants() -> None:
    p = NitrogenRateParams()
    assert p.mineralization_base_rate == 0.001
    assert p.nitrification_base_rate == 0.15
    assert p.nitrification_max_rate == 0.20
    assert p.denitrification_base_rate == 0.02
    assert p.volatilization_base_rate == 0.05
    assert p.volatilization_max_rate == 0.10
    # Clay modulation is loam-referenced (unchanged for loam realism profile).
    assert p.denit_clay_reference_pct == 22.0


def test_phosphorus_defaults_match_historical_constants() -> None:
    p = PhosphorusRateParams()
    assert p.mineralization_monthly_min == 0.005
    assert p.mineralization_monthly_max == 0.02
    assert p.fixation_weekly_min == 0.002
    assert p.fixation_weekly_max == 0.01
    assert p.fixation_clay_reference_pct == 22.0


def test_params_are_frozen() -> None:
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        NitrogenRateParams().mineralization_base_rate = 0.5  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        PhosphorusRateParams().fixation_weekly_min = 0.5  # type: ignore[misc]


def test_no_inline_rate_literals_remain_in_cycle_sources() -> None:
    """Validation step 3: no leftover inline magic rate scalars."""
    n_src = Path("agrogame/soil/nitrogen/cycle.py").read_text()
    p_src = Path("agrogame/soil/phosphorus/cycle.py").read_text()
    # Historical inline forms that must now come from params.
    assert "0.001 * temp_factor" not in n_src
    assert "0.15\n" not in n_src
    assert "0.05 * temp_factor" not in n_src
    assert "min(0.20, rate)" not in n_src
    assert "min(0.10, rate)" not in n_src
    assert "FIXATION_WEEKLY" not in p_src
    assert "0.005 / 30.0" not in p_src
    # Both cycles read their rate params.
    assert "self._params." in n_src
    assert "self._params." in p_src


# --- Custom params flow through (AC1) -------------------------------------


def test_custom_mineralization_rate_changes_output() -> None:
    profile = _profile("loam")
    bus = EventBus()
    state = SoilNitrogenState(profile)
    fast = NitrogenCycle(
        bus,
        state,
        profile=cast(Any, profile),
        params=NitrogenRateParams(mineralization_base_rate=0.002),
    )
    base_flux = NitrogenCycle(
        EventBus(), SoilNitrogenState(profile), profile=cast(Any, profile)
    ).daily_step(temperature_c=20.0)
    fast_flux = fast.daily_step(temperature_c=20.0)
    assert fast_flux.mineralized_kg_ha > base_flux.mineralized_kg_ha


# --- Clay modulation (AC3) -----------------------------------------------


def test_denitrification_scales_with_clay() -> None:
    """Finer texture -> more anaerobic microsites -> more denitrification."""
    sand = _profile("sand")  # clay_pct filled to 5% from texture
    clay = _profile("clay")  # clay_pct filled to 50% from texture

    sand_water = SoilWaterState(sand)
    _saturate(sand_water, sand)
    sand_flux = NitrogenCycle(
        EventBus(),
        SoilNitrogenState(sand),
        water_state=cast(Any, sand_water),
        profile=cast(Any, sand),
    ).daily_step(temperature_c=25.0)

    clay_water = SoilWaterState(clay)
    _saturate(clay_water, clay)
    clay_flux = NitrogenCycle(
        EventBus(),
        SoilNitrogenState(clay),
        water_state=cast(Any, clay_water),
        profile=cast(Any, clay),
    ).daily_step(temperature_c=25.0)

    assert clay_flux.denitrified_kg_ha > sand_flux.denitrified_kg_ha


def test_denitrification_neutral_at_reference_clay() -> None:
    """A loam (22% clay) profile matches an explicit no-clay baseline."""
    loam = _profile("loam")  # -> 22% clay == reference
    no_clay = _profile("loam", clay_pct=None)

    def _run(prof: SoilProfile) -> float:
        water = SoilWaterState(prof)
        _saturate(water, prof)
        return (
            NitrogenCycle(
                EventBus(),
                SoilNitrogenState(prof),
                water_state=cast(Any, water),
                profile=cast(Any, prof),
            )
            .daily_step(temperature_c=25.0)
            .denitrified_kg_ha
        )

    assert _run(loam) == _run(no_clay)


def test_phosphorus_fixation_scales_with_clay() -> None:
    """Clay/oxide-rich soils fix more P than sandy soils (Barrow 1983)."""
    sand = _profile("sand")
    clay = _profile("clay")

    sand_flux = PhosphorusCycle(
        EventBus(), SoilPhosphorusState(sand), profile=cast(Any, sand)
    ).daily_step(temperature_c=25.0, ph_by_layer=[6.0, 6.0, 6.0])
    clay_flux = PhosphorusCycle(
        EventBus(), SoilPhosphorusState(clay), profile=cast(Any, clay)
    ).daily_step(temperature_c=25.0, ph_by_layer=[6.0, 6.0, 6.0])

    assert clay_flux.fixed_kg_ha > sand_flux.fixed_kg_ha


def test_phosphorus_fixation_neutral_without_profile() -> None:
    """No profile -> clay multiplier is 1.0 (historical behaviour preserved)."""
    profile = _profile("loam")
    no_profile_flux = PhosphorusCycle(
        EventBus(), SoilPhosphorusState(profile)
    ).daily_step(temperature_c=25.0, ph_by_layer=[6.0, 6.0, 6.0])
    ref_flux = PhosphorusCycle(
        EventBus(), SoilPhosphorusState(profile), profile=cast(Any, profile)
    ).daily_step(temperature_c=25.0, ph_by_layer=[6.0, 6.0, 6.0])
    # loam == reference clay -> identical to the no-profile (neutral) case.
    assert no_profile_flux.fixed_kg_ha == ref_flux.fixed_kg_ha


def test_soil_presets_directory_exists() -> None:
    """Guard: realism suite depends on the loam preset used as reference."""
    assert Path("data/soils/presets.yaml").exists()
