"""Tests for the shared EnvironmentalCache nutrient-cycle component (#322)."""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.plant.roots.events import RootDistributionUpdated
from agrogame.soil.chemistry.events import SoilPHUpdated
from agrogame.soil.microbes.events import (
    MicrobialActivityComputed,
    MicrobialFBUpdated,
)
from agrogame.soil.nutrients import EnvironmentalCache


def test_defaults_are_configurable() -> None:
    bus = EventBus()
    cache = EnvironmentalCache(
        bus,
        3,
        initial_ph=6.8,
        initial_microbe_activity=0.9,
        initial_fungal_fraction=0.3,
    )
    assert cache.ph_by_layer == [6.8, 6.8, 6.8]
    assert cache.microbe_activity_by_layer == [0.9, 0.9, 0.9]
    assert cache.fungal_fraction_by_layer == [0.3, 0.3, 0.3]
    assert cache.root_fractions is None


def test_ph_handler_updates_in_range_only() -> None:
    bus = EventBus()
    cache = EnvironmentalCache(bus, 2, initial_ph=7.0)
    bus.emit(SoilPHUpdated(layer=1, ph=5.5))
    bus.emit(SoilPHUpdated(layer=9, ph=4.0))  # out of range, ignored
    assert cache.ph_by_layer == [7.0, 5.5]


def test_microbe_handlers_clamp_to_unit_interval() -> None:
    bus = EventBus()
    cache = EnvironmentalCache(bus, 2)
    bus.emit(
        MicrobialActivityComputed(
            layer=0, activity_index=2.0, wfps=0.5, ph=6.0, temperature_c=15.0
        )
    )
    bus.emit(MicrobialFBUpdated(layer=1, fungal_fraction=-0.5))
    assert cache.microbe_activity_by_layer[0] == 1.0
    assert cache.fungal_fraction_by_layer[1] == 0.0


def test_root_fractions_normalized_policy() -> None:
    """Nitrogen policy: clamp negatives, renormalize to sum 1, trim/pad."""
    bus = EventBus()
    cache = EnvironmentalCache(bus, 4, normalize_root_fractions=True)
    bus.emit(RootDistributionUpdated(fractions=(2.0, 2.0, -1.0)))
    assert cache.root_fractions == [0.5, 0.5, 0.0, 0.0]


def test_root_fractions_normalized_trims_excess() -> None:
    bus = EventBus()
    cache = EnvironmentalCache(bus, 2, normalize_root_fractions=True)
    bus.emit(RootDistributionUpdated(fractions=(1.0, 1.0, 2.0)))
    assert cache.root_fractions == [0.25, 0.25]


def test_root_fractions_raw_policy_pads_only() -> None:
    """Phosphorus policy: store as received, pad (never trim) to n_layers."""
    bus = EventBus()
    cache = EnvironmentalCache(bus, 4, normalize_root_fractions=False)
    bus.emit(RootDistributionUpdated(fractions=(2.0, 2.0, -1.0)))
    assert cache.root_fractions == [2.0, 2.0, -1.0, 0.0]


def test_selective_subscription_pH_only() -> None:
    """Micronutrient usage: only the pH handler is wired to the bus."""
    bus = EventBus()
    cache = EnvironmentalCache(bus, 2, subscribe_roots=False, subscribe_microbes=False)
    bus.emit(SoilPHUpdated(layer=0, ph=8.0))
    bus.emit(RootDistributionUpdated(fractions=(1.0, 1.0)))
    bus.emit(
        MicrobialActivityComputed(
            layer=0, activity_index=0.2, wfps=0.5, ph=6.0, temperature_c=15.0
        )
    )
    assert cache.ph_by_layer == [8.0, 7.0]
    # Root/microbe events must not have been consumed
    assert cache.root_fractions is None
    assert cache.microbe_activity_by_layer == [1.0, 1.0]
