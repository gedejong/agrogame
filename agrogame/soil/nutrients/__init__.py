"""Shared components across the nutrient cycles (N, P, micronutrients).

Currently exposes :class:`EnvironmentalCache`, the per-layer environmental
signal cache (pH, root fractions, microbe activity, fungal fraction) that
the individual cycles compose instead of hand-rolling identical handlers.
"""

from __future__ import annotations

from .environment_cache import EnvironmentalCache

__all__ = ["EnvironmentalCache"]
