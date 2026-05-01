"""Tests for biopore module (#215).

Validates root-channel biopore creation, exponential decay, tillage
destruction, compaction collapse, density caps, pore-network
integration, and the earthworm stub for #76.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.plant.roots.events import RootTurnoverOccurred
from agrogame.soil.aggregation.events import TillageApplied
from agrogame.soil.biopores import (
    BioporeCollapsed,
    BioporeCreated,
    BioporeModule,
    BioporeParams,
    BioporeState,
    BioporesRuntime,
)
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network import (
    PoreNetworkModule,
    PoreNetworkParams,
    PoreNetworkState,
)


# ---------- helpers ----------


def _loam() -> SoilProfile:
    return load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]


def _fresh(
    n_layers: int | None = None,
    profile: SoilProfile | None = None,
    params: BioporeParams | None = None,
) -> tuple[EventBus, BioporeModule, BioporeState, SoilProfile]:
    bus = EventBus()
    if profile is None:
        profile = _loam()
    if n_layers is None:
        n_layers = len(profile.layers)
    state = BioporeState.from_layers(n_layers)
    module = BioporeModule(params or BioporeParams(), state, event_bus=bus)
    return bus, module, state, profile


# ---------- Pre-work AC: RootTurnoverOccurred ----------


def test_root_turnover_event_emitted_with_per_layer_split() -> None:
    """RootModule._update_biomass emits per-layer turnover."""
    from agrogame.plant.roots.module import RootModule
    from agrogame.plant.roots.params import RootParams
    from agrogame.plant.roots.types import RootState

    bus = EventBus()
    events: list[RootTurnoverOccurred] = []
    bus.subscribe(RootTurnoverOccurred, events.append)

    state = RootState(biomass_g_m2=100.0, layer_fractions=[0.5, 0.3, 0.2])
    module = RootModule(RootParams(turnover_rate_per_day=0.02), event_bus=bus)
    module._update_biomass(state, daily_root_biomass_g_m2=0.0)

    assert len(events) == 1
    per_layer = events[0].per_layer_dead_mass_g_m2
    assert len(per_layer) == 3
    # 100 × 0.02 = 2.0 dead total, split 50/30/20%
    assert per_layer[0] == pytest.approx(1.0)
    assert per_layer[1] == pytest.approx(0.6)
    assert per_layer[2] == pytest.approx(0.4)


def test_root_turnover_event_skipped_without_layer_distribution() -> None:
    """No layer_fractions yet → no turnover event (pre-emergence)."""
    from agrogame.plant.roots.module import RootModule
    from agrogame.plant.roots.params import RootParams
    from agrogame.plant.roots.types import RootState

    bus = EventBus()
    events: list[RootTurnoverOccurred] = []
    bus.subscribe(RootTurnoverOccurred, events.append)

    state = RootState(biomass_g_m2=10.0, layer_fractions=None)
    module = RootModule(RootParams(turnover_rate_per_day=0.02), event_bus=bus)
    module._update_biomass(state, daily_root_biomass_g_m2=0.0)
    assert events == []


# ---------- Params + State ----------


def test_params_frozen() -> None:
    p = BioporeParams()
    with pytest.raises(AttributeError):
        p.conversion_factor = 99.0  # type: ignore[misc]


def test_volume_fraction_formula() -> None:
    """density × π × r² (m²) per layer, depth-independent."""
    vf = BioporeState.density_to_volume_fraction(100.0, 2.0)
    expected = 100.0 * math.pi * (0.002**2)
    assert vf == pytest.approx(expected)


def test_state_round_trip() -> None:
    s = BioporeState(
        density_per_m2=[100.0, 50.0],
        mean_radius_mm=[2.0, 1.5],
        volume_fraction=[1e-3, 5e-4],
    )
    restored = BioporeState.from_dict(s.to_dict())
    assert restored.density_per_m2 == s.density_per_m2
    assert restored.mean_radius_mm == s.mean_radius_mm


# ---------- Creation ----------


def test_creation_from_root_turnover() -> None:
    bus, module, state, profile = _fresh()
    events: list[BioporeCreated] = []
    bus.subscribe(BioporeCreated, events.append)

    # 1 g/m² dead roots in top layer → ~625 mm³ tissue at 0.8 g/cm³;
    # at conversion=0.5 → 312.5 mm³ biopore volume per m². Each pore
    # cross-section π × (0.002 m)² = 1.26e-5 m² ≈ 12.6 mm² × layer
    # depth. Density count derived.
    module.process_root_turnover([1.0, 0.5, 0.0] + [0.0] * (len(profile.layers) - 3))

    assert state.density_per_m2[0] > 0.0
    assert state.density_per_m2[1] > 0.0
    assert state.density_per_m2[2] == 0.0
    assert events[0].layer == 0
    assert events[0].density_delta > 0
    assert events[0].volume_delta > 0


def test_no_creation_when_turnover_zero() -> None:
    bus, module, state, _ = _fresh()
    events: list[BioporeCreated] = []
    bus.subscribe(BioporeCreated, events.append)
    module.process_root_turnover([0.0] * len(state.density_per_m2))
    assert events == []
    assert all(d == 0.0 for d in state.density_per_m2)


def test_density_capped_at_max() -> None:
    bus, module, state, profile = _fresh()
    # Pump 100 days of heavy turnover.
    for _ in range(100):
        module.process_root_turnover([50.0] + [0.0] * (len(profile.layers) - 1))
    assert state.density_per_m2[0] <= module.params.max_density_per_m2 + 1e-9


# ---------- Decay ----------


def test_decay_halves_density_after_half_life() -> None:
    params = BioporeParams(
        decay_half_life_days_topsoil=10.0, decay_half_life_days_subsoil=10.0
    )
    bus, module, state, profile = _fresh(params=params)
    state.density_per_m2[0] = 200.0
    state.recompute_volume_fraction()

    for _ in range(10):
        module.apply_decay(profile)

    assert state.density_per_m2[0] == pytest.approx(100.0, rel=1e-3)


def test_subsoil_decays_slower_than_topsoil() -> None:
    params = BioporeParams(
        decay_half_life_days_topsoil=30.0, decay_half_life_days_subsoil=300.0
    )
    bus, module, state, profile = _fresh(params=params)
    # Seed equal densities top and bottom.
    for i in range(len(state.density_per_m2)):
        state.density_per_m2[i] = 100.0
    state.recompute_volume_fraction()

    for _ in range(60):
        module.apply_decay(profile)

    top = state.density_per_m2[0]
    bottom = state.density_per_m2[-1]
    assert (
        top < bottom * 0.95
    ), f"Topsoil ({top:.2f}) should decay faster than subsoil ({bottom:.2f})"


# ---------- Tillage destruction ----------


def test_tillage_destroys_plow_layer_only() -> None:
    bus, module, state, profile = _fresh()
    for i in range(len(state.density_per_m2)):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    events: list[BioporeCollapsed] = []
    bus.subscribe(BioporeCollapsed, events.append)
    module.apply_tillage(intensity=1.0, profile=profile)

    # Top layer (within plow depth) lost density.
    assert state.density_per_m2[0] < 200.0
    # Find layers below plow depth — they should be unchanged.
    cumulative = 0.0
    plow_depth = module.params.plow_depth_cm
    for i, layer in enumerate(profile.layers):
        if cumulative >= plow_depth:
            assert (
                state.density_per_m2[i] == 200.0
            ), f"Layer {i} below plow line was modified"
        cumulative += layer.depth_cm
    assert any(e.cause == "tillage" for e in events)


def test_tillage_intensity_scales_destruction() -> None:
    params = BioporeParams(tillage_destruction_max_frac=0.7)
    bus, module, state, profile = _fresh(params=params)
    state.density_per_m2[0] = 200.0
    state.recompute_volume_fraction()

    module.apply_tillage(intensity=1.0, profile=profile)
    expected_loss = 200.0 * 0.7
    assert state.density_per_m2[0] == pytest.approx(200.0 - expected_loss)


def test_no_tillage_at_zero_intensity() -> None:
    bus, module, state, profile = _fresh()
    state.density_per_m2[0] = 200.0
    state.recompute_volume_fraction()
    module.apply_tillage(intensity=0.0, profile=profile)
    assert state.density_per_m2[0] == 200.0


# ---------- Compaction ----------


def test_compaction_proportional_to_intensity_and_moisture() -> None:
    bus, module, state, profile = _fresh()
    state.density_per_m2[0] = 200.0
    state.recompute_volume_fraction()

    events: list[BioporeCollapsed] = []
    bus.subscribe(BioporeCollapsed, events.append)

    module.apply_compaction(intensity=0.5, moisture_factor=0.8, profile=profile)
    # loss_frac = 0.5 × 0.8 × 0.4 = 0.16
    assert state.density_per_m2[0] == pytest.approx(200.0 * (1 - 0.16))
    assert any(e.cause == "compaction" for e in events)


def test_compaction_dry_soil_no_loss() -> None:
    bus, module, state, profile = _fresh()
    state.density_per_m2[0] = 200.0
    module.apply_compaction(intensity=1.0, moisture_factor=0.0, profile=profile)
    assert state.density_per_m2[0] == 200.0


# ---------- Pore-network integration ----------


def test_update_pore_network_adds_to_macro_within_budget() -> None:
    """Biopore volume feeds into pore_state.macro without breaking the
    saturation budget invariant from #211."""
    bus, module, state, profile = _fresh()
    n = len(profile.layers)
    pore_state = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)
    macro_before = list(pore_state.macro)

    # Set a moderate biopore density.
    for i in range(n):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    module.update_pore_network(pore_state, profile)

    for i, layer in enumerate(profile.layers):
        total = (
            pore_state.macro[i]
            + pore_state.meso[i]
            + pore_state.micro[i]
            + pore_state.crypto[i]
        )
        # Budget invariant must hold (within float tolerance).
        assert abs(total - layer.saturation) < 1e-6
        # Macro only grows.
        assert pore_state.macro[i] >= macro_before[i]


def test_update_pore_network_no_op_when_no_biopores() -> None:
    bus, module, state, profile = _fresh()
    n = len(profile.layers)
    pore_state = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)
    macro_before = list(pore_state.macro)
    module.update_pore_network(pore_state, profile)
    assert pore_state.macro == macro_before


# ---------- Earthworm stub (#76 forward-compat) ----------


def test_add_earthworm_biopores_increases_density() -> None:
    state = BioporeState.from_layers(3)
    state.add_earthworm_biopores(layer=0, count=50.0, mean_radius_mm=4.0)
    assert state.density_per_m2[0] == 50.0
    assert state.mean_radius_mm[0] == pytest.approx(4.0)
    assert state.volume_fraction[0] == pytest.approx(
        BioporeState.density_to_volume_fraction(50.0, 4.0)
    )


def test_add_earthworm_invalid_layer_safe() -> None:
    state = BioporeState.from_layers(3)
    state.add_earthworm_biopores(layer=99, count=10.0, mean_radius_mm=4.0)
    assert all(d == 0.0 for d in state.density_per_m2)


# ---------- Runtime wiring ----------


def test_runtime_subscribes_and_creates_on_turnover_event() -> None:
    bus = EventBus()
    profile = _loam()
    state = BioporeState.from_layers(len(profile.layers))
    module = BioporeModule(BioporeParams(), state, event_bus=bus)
    BioporesRuntime(event_bus=bus, module=module, profile=profile)

    bus.emit(
        RootTurnoverOccurred(
            per_layer_dead_mass_g_m2=tuple([1.0] + [0.0] * (len(profile.layers) - 1))
        )
    )
    assert state.density_per_m2[0] > 0.0


def test_runtime_tillage_event_destroys_biopores() -> None:
    bus = EventBus()
    profile = _loam()
    state = BioporeState.from_layers(len(profile.layers))
    module = BioporeModule(BioporeParams(), state, event_bus=bus)
    BioporesRuntime(event_bus=bus, module=module, profile=profile)

    state.density_per_m2[0] = 300.0
    state.recompute_volume_fraction()
    bus.emit(TillageApplied(intensity=1.0, macro_destroyed_frac=0.7))
    assert state.density_per_m2[0] < 300.0


# ---------- Realism: cover crop vs fallow + tillage decay ----------


def test_cover_crop_vs_fallow_density_ratio() -> None:
    """3-year continuous root turnover (cover crop) vs fallow + tillage.

    Ref: Six et al. 2004 — cover-crop biopore density >2× fallow.
    Test simulates 3 × 365 = 1095 daily cycles. Cover crop emits steady
    daily turnover (1 g/m² × layer_fractions). Fallow has zero turnover
    AND a tillage event each year.
    """
    profile = _loam()
    n = len(profile.layers)

    # Cover crop scenario
    cc_state = BioporeState.from_layers(n)
    cc_module = BioporeModule(BioporeParams(), cc_state)
    daily_dead = [0.6 / n] * n  # ~0.6 g/m²/day total dead-root mass
    for _ in range(365 * 3):
        cc_module.process_root_turnover(daily_dead)
        cc_module.apply_decay(profile)

    # Fallow + 1 tillage per year, no turnover
    f_state = BioporeState.from_layers(n)
    f_module = BioporeModule(BioporeParams(), f_state)
    for _year in range(3):
        for _ in range(365):
            f_module.apply_decay(profile)
        f_module.apply_tillage(intensity=1.0, profile=profile)

    cc_top = cc_state.density_per_m2[0]
    f_top = f_state.density_per_m2[0]
    assert cc_top > 2.0 * max(f_top, 1e-6), (
        f"Cover crop should hold ≥2× fallow biopores: cc={cc_top:.1f}, "
        f"fallow={f_top:.1f}"
    )


def test_tillage_plus_fallow_drives_density_to_zero() -> None:
    """Tillage every season + no replacement → biopores → 0 within 2 seasons."""
    profile = _loam()
    n = len(profile.layers)
    state = BioporeState.from_layers(n)
    module = BioporeModule(BioporeParams(), state)
    for i in range(n):
        state.density_per_m2[i] = 300.0
    state.recompute_volume_fraction()

    # Two full agricultural years of decay + annual tillage.
    initial = state.density_per_m2[0]
    for _season in range(2):
        for _ in range(365):
            module.apply_decay(profile)
        module.apply_tillage(intensity=1.0, profile=profile)

    # Top layer should be << 1% of starting density in the plow zone.
    final = state.density_per_m2[0]
    assert final < initial * 0.01, (
        f"Top biopore density {final:.2f} (started {initial:.0f}) "
        f"should approach zero within 2 seasons"
    )
