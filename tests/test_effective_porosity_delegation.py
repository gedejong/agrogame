"""Delegation of ``effective_porosity`` to the detailed pore network (#289).

``effective_porosity`` now returns the *drainable* porosity from the
pore-network breakdown (total - crypto) when a ``PoreNetworkState`` is
supplied, and falls back to the aggregation-shifted scalar otherwise.

These tests exercise **both** paths and pin the wiring at the
``WaterRuntime`` boundary. The measured detailed-vs-scalar shift for
``loam_temperate`` at default tilled aggregation is ~-10% (detailed lower,
because it excludes the tightly bound cryptopore/residual water). See PR
for the full table.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.aggregation.dynamic_state import effective_porosity
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.pore_network import (
    PoreNetworkModule,
    PoreNetworkParams,
    PoreNetworkState,
)
from agrogame.soil.water.runtime import WaterRuntime
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes

_PRESETS = Path("data/soils/presets.yaml")


def _loam_profile():
    return load_soil_presets(_PRESETS).soils["loam_temperate"]


def _computed_pore_state(profile, agg: SoilAggregationState) -> PoreNetworkState:
    state = PoreNetworkState.empty(len(profile.layers))
    PoreNetworkModule(PoreNetworkParams(), state).compute(profile, agg)
    return state


# --- scalar fallback (backward-compatible) ---


def test_scalar_fallback_no_pore_state() -> None:
    """No pore_state → existing scalar formula; macro=0.25 is the neutral point."""
    assert abs(effective_porosity(0.45, 0.25) - 0.45) < 1e-9
    # Above/below the tilled reference shifts up/down.
    assert effective_porosity(0.45, 0.60) > 0.45
    assert effective_porosity(0.45, 0.05) < 0.45


def test_scalar_fallback_when_layer_missing() -> None:
    """pore_state without a valid layer index falls back to the scalar path."""
    pore = PoreNetworkState(
        macro=[0.10], meso=[0.20], micro=[0.07], crypto=[0.05], connectivity=[0.2]
    )
    # layer=None → scalar
    assert abs(effective_porosity(0.45, 0.25, pore_state=pore) - 0.45) < 1e-9
    # layer out of range → scalar (defensive, no IndexError)
    assert abs(effective_porosity(0.45, 0.25, pore_state=pore, layer=5) - 0.45) < 1e-9


# --- detailed delegation ---


def test_detailed_returns_total_minus_crypto() -> None:
    """Detailed path returns drainable porosity = macro + meso + micro."""
    pore = PoreNetworkState(
        macro=[0.10], meso=[0.20], micro=[0.07], crypto=[0.05], connectivity=[0.2]
    )
    # total = 0.42, crypto = 0.05 → 0.37 (macro+meso+micro).
    got = effective_porosity(0.45, 0.25, pore_state=pore, layer=0)
    assert abs(got - 0.37) < 1e-9
    # Base saturation and macro_frac are ignored on the detailed path.
    assert abs(effective_porosity(0.99, 0.99, pore_state=pore, layer=0) - 0.37) < 1e-9


def test_detailed_clamped_to_physical_bounds() -> None:
    """Detailed drainable porosity is clamped to [0.30, 0.60]."""
    hi = PoreNetworkState(
        macro=[0.40], meso=[0.30], micro=[0.10], crypto=[0.02], connectivity=[0.5]
    )
    assert effective_porosity(0.5, 0.5, pore_state=hi, layer=0) == 0.60
    lo = PoreNetworkState(
        macro=[0.05], meso=[0.08], micro=[0.04], crypto=[0.10], connectivity=[0.1]
    )
    assert effective_porosity(0.4, 0.1, pore_state=lo, layer=0) == 0.30


def test_detailed_differs_from_scalar_loam_temperate() -> None:
    """Detailed vs scalar shift for loam_temperate is a documented ~-10%.

    Detailed excludes cryptopore (residual, ~0.045 at 22% clay) water that
    the scalar treats as part of total porosity. Ref: Luxmoore 1981 SSSAJ;
    Rawls et al. 1982 Trans. ASAE (theta_r vs clay%).
    """
    profile = _loam_profile()
    agg = SoilAggregationState.from_layers(len(profile.layers))  # macro=0.25
    pore = _computed_pore_state(profile, agg)
    for i, layer in enumerate(profile.layers):
        scalar = effective_porosity(layer.saturation, agg.macro[i])
        detailed = effective_porosity(
            layer.saturation, agg.macro[i], pore_state=pore, layer=i
        )
        rel = (detailed - scalar) / scalar
        assert detailed < scalar, "detailed should exclude bound cryptopore water"
        assert -0.13 < rel < -0.08, f"layer {i} rel shift {rel:.3%} outside ~-10%"
        # Detailed value stays physically plausible for loam.
        assert 0.37 <= detailed <= 0.41


def test_detailed_is_aggregation_invariant() -> None:
    """Delegating drops the aggregation→porosity feedback (refinement note).

    The detailed value depends only on texture (residual water), so it is
    identical across degraded and well-aggregated states, whereas the
    scalar path moves. This is the intended behaviour change under #289.
    """
    profile = _loam_profile()
    n = len(profile.layers)
    detailed_vals = []
    scalar_vals = []
    for macro in (0.05, 0.25, 0.60):
        agg = SoilAggregationState.from_layers(n)
        agg.micro = [max(0.0, 1.0 - macro - 0.35)] * n
        agg.meso = [0.35] * n
        agg.macro = [macro] * n
        pore = _computed_pore_state(profile, agg)
        detailed_vals.append(
            effective_porosity(
                profile.layers[0].saturation, macro, pore_state=pore, layer=0
            )
        )
        scalar_vals.append(effective_porosity(profile.layers[0].saturation, macro))
    # Detailed: invariant to aggregation.
    assert max(detailed_vals) - min(detailed_vals) < 1e-9
    # Scalar: responds to aggregation (feedback that delegation removes).
    assert max(scalar_vals) - min(scalar_vals) > 0.03


# --- WaterRuntime boundary wiring ---


class _RecordingWaterModel:
    """Stub that records the porosity_overrides it receives."""

    def __init__(self) -> None:
        self.seen_porosity: list[float] | None = None

    def daily_step(
        self,
        profile,
        state,
        drivers,
        *,
        ksat_factors=None,
        porosity_overrides=None,
    ) -> WaterFluxes:
        self.seen_porosity = porosity_overrides
        return WaterFluxes(
            runoff_mm=0.0,
            deep_drainage_mm=0.0,
            evap_mm=0.0,
            storage_change_mm=0.0,
        )


def test_water_runtime_passes_detailed_porosity() -> None:
    """WaterRuntime feeds pore-network-derived porosity into the water model."""
    profile = _loam_profile()
    n = len(profile.layers)
    agg = SoilAggregationState.from_layers(n)
    pore = _computed_pore_state(profile, agg)

    bus = EventBus()
    model = _RecordingWaterModel()
    runtime = WaterRuntime(
        bus,
        model,  # type: ignore[arg-type]
        profile,
        SoilWaterState(profile),
        agg_state=agg,
        pore_state=pore,
    )
    assert runtime is not None  # constructed + subscribed
    bus.emit(
        DayTick(
            sim_date=date(2024, 5, 1),
            phase="water",
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
        )
    )
    assert model.seen_porosity is not None
    expected = [
        effective_porosity(
            profile.layers[i].saturation, agg.macro[i], pore_state=pore, layer=i
        )
        for i in range(n)
    ]
    assert model.seen_porosity == expected


def test_water_runtime_scalar_without_pore_state() -> None:
    """Without pore_state, WaterRuntime keeps the scalar overrides (back-compat)."""
    profile = _loam_profile()
    n = len(profile.layers)
    agg = SoilAggregationState.from_layers(n)

    bus = EventBus()
    model = _RecordingWaterModel()
    WaterRuntime(
        bus,
        model,  # type: ignore[arg-type]
        profile,
        SoilWaterState(profile),
        agg_state=agg,
    )
    bus.emit(
        DayTick(
            sim_date=date(2024, 5, 1),
            phase="water",
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
        )
    )
    assert model.seen_porosity is not None
    expected = [
        effective_porosity(profile.layers[i].saturation, agg.macro[i]) for i in range(n)
    ]
    assert model.seen_porosity == expected
