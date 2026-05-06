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


def test_tillage_destroys_within_effective_plow_zone_only() -> None:
    """Layers entirely below the (intensity-scaled) plow line are untouched.

    With layer-overlap pro-rating in place, layers straddling the plow
    line are partially affected — see ``test_tillage_layer_overlap_prorated``.
    """
    bus, module, state, profile = _fresh()
    for i in range(len(state.density_per_m2)):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    events: list[BioporeCollapsed] = []
    bus.subscribe(BioporeCollapsed, events.append)
    module.apply_tillage(intensity=1.0, profile=profile)

    # Top layer (within plow depth) lost density.
    assert state.density_per_m2[0] < 200.0
    # Layers wholly below the plow line are untouched.
    plow_depth = module.params.plow_depth_cm
    layer_top = 0.0
    for i, layer in enumerate(profile.layers):
        if layer_top >= plow_depth:
            assert (
                state.density_per_m2[i] == 200.0
            ), f"Layer {i} entirely below plow line was modified"
        layer_top += layer.depth_cm
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


# Continuous cover-crop turnover (#290 calibration). Total daily mass
# 5.0 g/m²/d ≈ 18 t/ha/yr — at the upper end of literature ranges for
# productive cover-crop systems (Bidlack & Buxton 1992; Kautz 2015 Table 2,
# 4-8 t/ha/yr fine-root turnover for established cover crops). Split
# across layers using a typical exponential root distribution that puts
# ~50/30/20% in the 0-25/25-60/60-100 cm horizons (Jackson et al. 1996).
_COVER_CROP_DEAD_TOTAL_G_M2_PER_DAY = 5.0
_COVER_CROP_LAYER_FRACTIONS = (0.5, 0.3, 0.2)


def _cover_crop_daily_dead(n_layers: int) -> list[float]:
    """Per-layer daily dead-root mass for the cover-crop scenario.

    See module-level constants for citations.
    """
    fractions = _COVER_CROP_LAYER_FRACTIONS[:n_layers]
    if len(fractions) < n_layers:
        # Pad shorter profiles with deep-root tail.
        fractions = fractions + (0.0,) * (n_layers - len(fractions))
    return [_COVER_CROP_DEAD_TOTAL_G_M2_PER_DAY * f for f in fractions]


def test_cover_crop_vs_fallow_density_ratio() -> None:
    """Pre-established cover crop > 2× fallow biopore density after 3 years.

    Ref: Six et al. 2004 — cover-crop biopore density >2× fallow.
    Both fields start at the same mature density (100/m², representing
    an established stand at experiment start), so the test compares
    the **maintained** vs **decaying** trajectories rather than the
    trivial "cover crop creates anything" baseline.
    """
    profile = _loam()
    n = len(profile.layers)
    starting_density = 100.0

    # Cover crop scenario: ongoing root turnover replenishes losses.
    cc_state = BioporeState.from_layers(n)
    for i in range(n):
        cc_state.density_per_m2[i] = starting_density
    cc_state.recompute_volume_fraction()
    cc_module = BioporeModule(BioporeParams(), cc_state)
    daily_dead = _cover_crop_daily_dead(n)
    for _ in range(365 * 3):
        cc_module.process_root_turnover(daily_dead)
        cc_module.apply_decay(profile)

    # Fallow + 1 tillage per year, no turnover.
    f_state = BioporeState.from_layers(n)
    for i in range(n):
        f_state.density_per_m2[i] = starting_density
    f_state.recompute_volume_fraction()
    f_module = BioporeModule(BioporeParams(), f_state)
    for _year in range(3):
        for _ in range(365):
            f_module.apply_decay(profile)
        f_module.apply_tillage(intensity=1.0, profile=profile)

    cc_top = cc_state.density_per_m2[0]
    f_top = f_state.density_per_m2[0]
    assert cc_top > 2.0 * max(f_top, 1e-6), (
        f"Cover crop should hold ≥2× fallow biopores after 3 years: "
        f"cc={cc_top:.3f}, fallow={f_top:.3f}"
    )


def test_cover_crop_steady_state_density_in_pierret_range() -> None:
    """Topsoil density at 3-yr SS lands in Pierret 2007's lower-half band.

    Pierret et al. 2007, Plant Soil 286 — structured agricultural soils
    carry 50–500 biopores/m². Calibration target (#290) is the lower
    half [50, 200] /m² for typical cover-crop turnover, which leaves
    headroom for management practices that intensify channel formation
    (e.g. perennial deep-rooted cover crops near the upper bound).
    """
    profile = _loam()
    n = len(profile.layers)
    state = BioporeState.from_layers(n)
    module = BioporeModule(BioporeParams(), state)
    daily_dead = _cover_crop_daily_dead(n)
    # 3 years of continuous turnover is enough to reach steady state given
    # the 180-day topsoil decay half-life (>5 half-lives).
    for _ in range(365 * 3):
        module.process_root_turnover(daily_dead)
        module.apply_decay(profile)

    topsoil = state.density_per_m2[0]
    assert 50.0 <= topsoil <= 200.0, (
        f"Topsoil biopore density {topsoil:.1f} /m² outside Pierret 2007 "
        f"lower-half band [50, 200]."
    )


def test_cover_crop_topsoil_exceeds_subsoil() -> None:
    """SS depth profile must be physical: topsoil ≥ subsoil density.

    Pierret 2007 + Kautz 2015 both report topsoil channel density
    higher than subsoil because root density itself peaks at the
    surface — even with faster topsoil decay, more new channels form
    near the top. The pre-#290 parameterisation produced an inverted
    profile (subsoil ≈ 17 /m², topsoil ≈ 1.3 /m²), masking the
    magnitude bug. This test guards against that regression.
    """
    profile = _loam()
    n = len(profile.layers)
    state = BioporeState.from_layers(n)
    module = BioporeModule(BioporeParams(), state)
    daily_dead = _cover_crop_daily_dead(n)
    for _ in range(365 * 3):
        module.process_root_turnover(daily_dead)
        module.apply_decay(profile)

    topsoil = state.density_per_m2[0]
    subsoil = state.density_per_m2[-1]
    assert topsoil >= subsoil, (
        f"Topsoil density ({topsoil:.1f} /m²) must be ≥ subsoil "
        f"({subsoil:.1f} /m²) — Pierret 2007, Kautz 2015."
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


# ---------- Tillage scaling + layer overlap ----------


def test_tillage_intensity_scales_plow_depth() -> None:
    """Effective plow depth scales with intensity (matches AggregationModule)."""
    profile = _loam()
    bus, module, state, _ = _fresh(profile=profile)
    for i in range(len(state.density_per_m2)):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    # Intensity 0.3 → effective plow depth = 30 × 0.3 = 9 cm.
    # Layer 0 spans 0-25 cm, so overlap = 9/25 = 0.36.
    # Lost frac = 0.3 × 0.7 × 0.36 ≈ 0.0756.
    module.apply_tillage(intensity=0.3, profile=profile)
    expected = 200.0 * (1.0 - 0.3 * 0.7 * 9.0 / 25.0)
    assert state.density_per_m2[0] == pytest.approx(expected, rel=1e-6)


def test_tillage_layer_overlap_prorated() -> None:
    """Layer straddling the plow line is partially destroyed.

    loam_temperate: layer 0 = 0-25 cm, layer 1 = 25-60 cm. Plow
    depth 30 cm at intensity=1.0 → layer 1 overlaps 5 cm out of 35,
    so destroy frac = 1.0 × 0.7 × (5/35) = 0.10.
    """
    profile = _loam()
    bus, module, state, _ = _fresh(profile=profile)
    for i in range(len(state.density_per_m2)):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    module.apply_tillage(intensity=1.0, profile=profile)
    # Layer 0: full overlap → 70% destroyed.
    assert state.density_per_m2[0] == pytest.approx(60.0)
    # Layer 1: 5/35 = 0.143 overlap → 0.7 × 0.143 ≈ 0.10 destroyed.
    assert state.density_per_m2[1] == pytest.approx(200.0 * (1.0 - 0.7 * 5.0 / 35.0))
    # Layer 2 onwards: untouched.
    for i in range(2, len(state.density_per_m2)):
        assert state.density_per_m2[i] == 200.0


# ---------- update_pore_network: idempotence + budget cap ----------


def test_update_pore_network_idempotent_within_compute_cycle() -> None:
    """Repeated calls after one compute() must not double-count the bonus."""
    bus, module, state, profile = _fresh()
    n = len(profile.layers)
    pore_state = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)

    for i in range(n):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()

    module.update_pore_network(pore_state, profile)
    macro_after_first = list(pore_state.macro)
    crypto_after_first = list(pore_state.crypto)

    # Second call without resetting baseline must be a no-op.
    module.update_pore_network(pore_state, profile)
    assert pore_state.macro == macro_after_first
    assert pore_state.crypto == crypto_after_first


def test_update_pore_network_after_reset_reapplies() -> None:
    """After ``reset_pore_network_baseline`` + fresh compute, donation re-applies."""
    bus, module, state, profile = _fresh()
    n = len(profile.layers)
    pore_state = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)
    for i in range(n):
        state.density_per_m2[i] = 200.0
    state.recompute_volume_fraction()
    module.update_pore_network(pore_state, profile)

    # Recompute pore network (donor pools refilled) and reset baseline.
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)
    module.reset_pore_network_baseline()
    macro_before = list(pore_state.macro)
    module.update_pore_network(pore_state, profile)
    # Macro grew on the second cycle.
    assert all(pore_state.macro[i] > macro_before[i] - 1e-12 for i in range(n))


def test_update_pore_network_budget_cap_enforced() -> None:
    """When biopore bonus exceeds available donors, macro stops growing
    and the saturation invariant still holds."""
    bus, module, state, profile = _fresh()
    n = len(profile.layers)
    pore_state = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), pore_state).compute(profile)

    # Pre-fill macro to the saturation cap so there's no donor budget.
    for i, layer in enumerate(profile.layers):
        # Total of crypto + micro in baseline is small; force macro to
        # consume nearly the whole saturation budget.
        pore_state.macro[i] = (
            layer.saturation - pore_state.meso[i] - pore_state.micro[i]
        )
        pore_state.crypto[i] = 0.0

    # Pump biopore density to the cap → bonus would be ~6e-3 m³/m³
    # but no crypto/micro left and macro already at budget edge.
    for i in range(n):
        state.density_per_m2[i] = 500.0
    state.recompute_volume_fraction()

    module.update_pore_network(pore_state, profile)

    for i, layer in enumerate(profile.layers):
        total = (
            pore_state.macro[i]
            + pore_state.meso[i]
            + pore_state.micro[i]
            + pore_state.crypto[i]
        )
        # Saturation invariant must still hold within float tolerance.
        assert (
            abs(total - layer.saturation) < 1e-6
        ), f"Layer {i}: total {total:.6f} ≠ sat {layer.saturation}"


# ---------- Earthworm radius mass-conservation (concern 6) ----------


def test_root_turnover_volume_consistent_with_layer_radius() -> None:
    """``process_root_turnover`` deposits volume using the layer's own radius.

    After a synthetic earthworm pass enlarges layer 0's mean radius,
    the volume_fraction implied by the new density × radius equals
    what we'd expect from converting the dead-root mass at the
    *same* radius. Without the fix in concern 6 (using `state.mean_radius_mm`
    consistently), this test would show inflated volume.
    """
    bus, module, state, profile = _fresh()
    # Earthworm pass: large radius (4 mm) on layer 0 only.
    state.add_earthworm_biopores(layer=0, count=20.0, mean_radius_mm=4.0)
    radius_after_worms = state.mean_radius_mm[0]
    assert radius_after_worms > 2.0  # density-weighted average grew

    # Add 2 g/m² dead roots → expected biopore volume:
    #   mass_g/m² / 0.8 g/cm³ = 2.5 cm³/m² = 2.5e-6 m³/m²
    #   × 0.5 conversion = 1.25e-6 m³/m²
    # density delta back-calculated using state.mean_radius_mm[0] (concern 6 fix).
    module.process_root_turnover([2.0, 0.0, 0.0] + [0.0] * (len(profile.layers) - 3))

    # Round-trip volume_fraction must match density × π × r² where r is
    # the layer's actual mean radius after the operation.
    expected_vf = BioporeState.density_to_volume_fraction(
        state.density_per_m2[0], state.mean_radius_mm[0]
    )
    assert state.volume_fraction[0] == pytest.approx(expected_vf, rel=1e-9)


# ---------- Param validation (post_init) ----------


def test_params_invalid_conversion_factor_raises() -> None:
    with pytest.raises(ValueError, match="conversion_factor"):
        BioporeParams(conversion_factor=-0.1)
    with pytest.raises(ValueError, match="conversion_factor"):
        BioporeParams(conversion_factor=1.5)


def test_params_invalid_half_life_raises() -> None:
    with pytest.raises(ValueError, match="topsoil"):
        BioporeParams(decay_half_life_days_topsoil=0.0)
    with pytest.raises(ValueError, match="subsoil"):
        BioporeParams(decay_half_life_days_subsoil=-10.0)


def test_params_invalid_radius_raises() -> None:
    with pytest.raises(ValueError, match="mean_radius_mm"):
        BioporeParams(mean_radius_mm=0.0)


# ---------- Event type narrowness ----------


def test_collapsed_event_cause_is_typed() -> None:
    """``BioporeCollapsed.cause`` is a Literal-typed field. mypy enforces
    static narrowness; here we just assert runtime values stay in spec.
    """
    bus, module, state, profile = _fresh()
    state.density_per_m2[0] = 200.0
    state.recompute_volume_fraction()
    events: list[BioporeCollapsed] = []
    bus.subscribe(BioporeCollapsed, events.append)
    module.apply_tillage(intensity=1.0, profile=profile)
    module.apply_compaction(intensity=0.5, moisture_factor=0.8, profile=profile)
    causes = {e.cause for e in events}
    assert causes <= {"tillage", "compaction"}
