"""Tests covering missing lines in agrogame/plant/roots/module.py."""

from __future__ import annotations

from pathlib import Path

from agrogame.events import EventBus
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.soil.phenology import PhenologyStage


def _profile() -> SoilProfile:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    return lib.soils["loam_temperate"]


# ---------------------------------------------------------------------------
# _stage_multiplier with custom stage_multipliers (line 22)
# ---------------------------------------------------------------------------


def test_custom_stage_multipliers() -> None:
    """Cover line 22 (custom stage_multipliers dict)."""
    mults = {PhenologyStage.VEGETATIVE: 0.8, PhenologyStage.FLOWERING: 0.3}
    roots = RootModule(RootParams(stage_multipliers=mults))
    assert roots._stage_multiplier(PhenologyStage.VEGETATIVE) == 0.8
    assert roots._stage_multiplier(PhenologyStage.FLOWERING) == 0.3
    # Stage not in dict falls to defaults
    assert roots._stage_multiplier(PhenologyStage.MATURITY) == 0.3


# ---------------------------------------------------------------------------
# _uniform_distribution (lines 60-90)
# ---------------------------------------------------------------------------


def test_uniform_distribution_continuous() -> None:
    """Cover lines 60-90 in _uniform_distribution with continuous=True."""
    profile = _profile()
    fracs = RootModule._uniform_distribution(profile, depth_cm=40.0, continuous=True)
    assert abs(sum(fracs) - 1.0) < 1e-6


def test_uniform_distribution_stepwise() -> None:
    """Cover lines 60-90 with continuous=False (line 80 branch)."""
    profile = _profile()
    fracs = RootModule._uniform_distribution(profile, depth_cm=40.0, continuous=False)
    # stepwise: boundary layer gets 0 fraction
    assert abs(sum(fracs) - 1.0) < 1e-6


def test_uniform_distribution_zero_depth() -> None:
    """Cover line 67-68: depth_cm <= top for all layers."""
    profile = _profile()
    fracs = RootModule._uniform_distribution(profile, depth_cm=0.0, continuous=True)
    assert all(f == 0.0 for f in fracs)


# ---------------------------------------------------------------------------
# _exponential_distribution with continuous=False (lines 115-116)
# ---------------------------------------------------------------------------


def test_exponential_distribution_stepwise() -> None:
    """Cover lines 115-116 in _exponential_distribution (continuous=False)."""
    profile = _profile()
    fracs = RootModule._exponential_distribution(
        profile, depth_cm=60.0, scale_cm=30.0, continuous=False
    )
    assert abs(sum(fracs) - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# _taproot_distribution with continuous=False (lines 147-149)
# ---------------------------------------------------------------------------


def test_taproot_distribution_stepwise() -> None:
    """Cover lines 147-149 in _taproot_distribution (continuous=False)."""
    profile = _profile()
    fracs = RootModule._taproot_distribution(
        profile, depth_cm=60.0, scale_cm=30.0, continuous=False
    )
    assert abs(sum(fracs) - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# _taproot_distribution lines 137-138 (depth_cm <= top)
# ---------------------------------------------------------------------------


def test_taproot_distribution_zero_depth() -> None:
    """Cover lines 137-138: depth_cm is 0 so all layers get 0 weight."""
    profile = _profile()
    fracs = RootModule._taproot_distribution(
        profile, depth_cm=0.0, scale_cm=30.0, continuous=True
    )
    assert all(f == 0.0 for f in fracs)


# ---------------------------------------------------------------------------
# _update_distribution with profile=None (line 177)
# ---------------------------------------------------------------------------


def test_update_distribution_no_profile() -> None:
    """Cover line 177 (skip when profile is None)."""
    roots = RootModule(RootParams())
    state = RootState(current_depth_cm=20.0)
    roots._update_distribution(state, profile=None, nutrient_signal=None)
    assert state.layer_fractions is None


# ---------------------------------------------------------------------------
# _update_biomass emitting events (line 221)
# ---------------------------------------------------------------------------


def test_update_biomass_emits_event() -> None:
    """Cover line 221 (RootBiomassUpdated event)."""
    bus = EventBus()
    captured = []
    from agrogame.plant.roots.events import RootBiomassUpdated

    bus.subscribe(RootBiomassUpdated, lambda e: captured.append(e))
    roots = RootModule(RootParams(turnover_rate_per_day=0.0), event_bus=bus)
    state = RootState(current_depth_cm=20.0, biomass_g_m2=0.0)
    roots._update_biomass(state, daily_root_biomass_g_m2=10.0)
    assert len(captured) == 1
    assert captured[0].biomass_g_m2 == 10.0


# ---------------------------------------------------------------------------
# root_shoot_ratio edge cases (line 241)
# ---------------------------------------------------------------------------


def test_root_shoot_ratio_zero_shoot_zero_root() -> None:
    """Cover line 241 (zero root, zero shoot)."""
    assert RootModule.root_shoot_ratio(0.0, 0.0) == 0.0


def test_root_shoot_ratio_zero_shoot_nonzero_root() -> None:
    """Cover line 241 (inf when root > 0 and shoot == 0)."""
    assert RootModule.root_shoot_ratio(10.0, 0.0) == float("inf")


# ---------------------------------------------------------------------------
# daily_step with uniform distribution (line 177 in _update_distribution)
# ---------------------------------------------------------------------------


def test_daily_step_uniform_distribution() -> None:
    """Cover line 177 in _update_distribution (uniform branch)."""
    profile = _profile()
    roots = RootModule(RootParams(distribution="uniform"))
    state = RootState(current_depth_cm=30.0)
    fluxes = roots.daily_step(state, profile, PhenologyStage.VEGETATIVE)
    assert fluxes.depth_inc_cm >= 0.0
    assert state.layer_fractions is not None
