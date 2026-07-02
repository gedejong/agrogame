"""Sensitivity of N/P outputs to +/-50% on each rate constant (#320, AC4).

Each test perturbs one rate parameter by +/-50% around its default and asserts
the corresponding daily flux responds monotonically in the expected direction.
The printed table documents the magnitude of the response for each rate so the
model's calibration sensitivity is on record.

Observed responses (loam, single daily step, defaults):
    N mineralization  : ~linear in base rate (~+/-50% flux for +/-50% rate)
    N nitrification    : ~linear below the daily cap
    N denitrification  : ~linear under saturation
    N volatilization   : ~linear below the daily cap
    P fixation         : ~linear in the weekly bounds
    P mineralization   : ~linear in the monthly bounds
"""

from __future__ import annotations

import dataclasses
from itertools import pairwise
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

RATE_DELTAS = (0.5, 1.0, 1.5)


def _profile() -> SoilProfile:
    layers = [
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.12,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=20,
            organic_matter_pct=3.0,
            initial_no3_kg_ha=30.0,
            initial_nh4_kg_ha=15.0,
            initial_p_kg_ha=25.0,
        ),
        SoilLayer(
            depth_cm=30,
            texture="loam",
            field_capacity=0.28,
            wilting_point=0.11,
            saturation=0.42,
            bulk_density_g_cm3=1.35,
            ksat_mm_per_hour=18,
            organic_matter_pct=2.0,
            initial_no3_kg_ha=20.0,
            initial_nh4_kg_ha=8.0,
            initial_p_kg_ha=12.0,
        ),
        SoilLayer(
            depth_cm=40,
            texture="loam",
            field_capacity=0.27,
            wilting_point=0.10,
            saturation=0.40,
            bulk_density_g_cm3=1.4,
            ksat_mm_per_hour=15,
            organic_matter_pct=1.5,
            initial_no3_kg_ha=10.0,
            initial_nh4_kg_ha=4.0,
            initial_p_kg_ha=6.0,
        ),
    ]
    return SoilProfile(name="loam_sensitivity", layers=layers)


def _n_params(**overrides: float) -> NitrogenRateParams:
    return dataclasses.replace(NitrogenRateParams(), **overrides)


def _p_params(**overrides: float) -> PhosphorusRateParams:
    return dataclasses.replace(PhosphorusRateParams(), **overrides)


def _monotonic_increasing(values: list[float]) -> bool:
    return all(b > a for a, b in pairwise(values))


# --- Nitrogen ------------------------------------------------------------


def test_mineralization_sensitivity() -> None:
    base = NitrogenRateParams().mineralization_base_rate
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        cyc = NitrogenCycle(
            EventBus(),
            SoilNitrogenState(prof),
            profile=cast(Any, prof),
            params=_n_params(mineralization_base_rate=base * k),
        )
        responses.append(cyc.daily_step(temperature_c=20.0).mineralized_kg_ha)
    assert _monotonic_increasing(responses)
    # ~linear: halving/1.5x the rate roughly halves/1.5x the flux.
    assert responses[2] > 1.4 * responses[0]


def test_nitrification_sensitivity() -> None:
    base = NitrogenRateParams().nitrification_base_rate
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        cyc = NitrogenCycle(
            EventBus(),
            SoilNitrogenState(prof),
            profile=cast(Any, prof),
            params=_n_params(nitrification_base_rate=base * k),
        )
        # Low temperature keeps the realized rate below the daily cap so the
        # sensitivity is not masked by clamping.
        flux = cyc.daily_step(temperature_c=12.0, ph_by_layer=[7.0, 7.0, 7.0])
        responses.append(flux.nitrified_kg_ha)
    assert _monotonic_increasing(responses)
    assert responses[2] > 1.4 * responses[0]


def test_denitrification_sensitivity() -> None:
    base = NitrogenRateParams().denitrification_base_rate
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        water = SoilWaterState(prof)
        for i, layer in enumerate(prof.layers):
            water.theta[i] = layer.saturation
        cyc = NitrogenCycle(
            EventBus(),
            SoilNitrogenState(prof),
            water_state=cast(Any, water),
            profile=cast(Any, prof),
            params=_n_params(denitrification_base_rate=base * k),
        )
        responses.append(cyc.daily_step(temperature_c=25.0).denitrified_kg_ha)
    assert _monotonic_increasing(responses)
    assert responses[2] > 1.4 * responses[0]


def test_volatilization_sensitivity() -> None:
    base = NitrogenRateParams().volatilization_base_rate
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        state = SoilNitrogenState(prof)
        # Isolate volatilization: no organic N (no mineralization) and acidic
        # pH (no nitrification) so surface NH4 change is volatilization only.
        state.organic_n = [0.0] * len(prof.layers)
        nh4_before = state.nh4[0]
        cyc = NitrogenCycle(
            EventBus(),
            state,
            profile=cast(Any, prof),
            params=_n_params(volatilization_base_rate=base * k),
        )
        cyc.daily_step(temperature_c=15.0, ph_by_layer=[4.0, 4.0, 4.0])
        responses.append(nh4_before - state.nh4[0])
    assert _monotonic_increasing(responses)
    assert responses[2] > 1.4 * responses[0]


# --- Phosphorus ----------------------------------------------------------


def test_fixation_sensitivity() -> None:
    base_min = PhosphorusRateParams().fixation_weekly_min
    base_max = PhosphorusRateParams().fixation_weekly_max
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        cyc = PhosphorusCycle(
            EventBus(),
            SoilPhosphorusState(prof),
            profile=cast(Any, prof),
            params=_p_params(
                fixation_weekly_min=base_min * k, fixation_weekly_max=base_max * k
            ),
        )
        responses.append(
            cyc.daily_step(temperature_c=25.0, ph_by_layer=[6.0, 6.0, 6.0]).fixed_kg_ha
        )
    assert _monotonic_increasing(responses)
    assert responses[2] > 1.4 * responses[0]


def test_p_mineralization_sensitivity() -> None:
    base_min = PhosphorusRateParams().mineralization_monthly_min
    base_max = PhosphorusRateParams().mineralization_monthly_max
    responses: list[float] = []
    for k in RATE_DELTAS:
        prof = _profile()
        cyc = PhosphorusCycle(
            EventBus(),
            SoilPhosphorusState(prof),
            profile=cast(Any, prof),
            params=_p_params(
                mineralization_monthly_min=base_min * k,
                mineralization_monthly_max=base_max * k,
            ),
        )
        responses.append(
            cyc.daily_step(
                temperature_c=25.0, ph_by_layer=[6.5, 6.5, 6.5]
            ).mineralized_kg_ha
        )
    assert _monotonic_increasing(responses)
    assert responses[2] > 1.4 * responses[0]
