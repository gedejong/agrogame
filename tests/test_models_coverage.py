"""Tests covering missing lines in params/models.py and soil/models.py."""

from __future__ import annotations

import pytest

from agrogame.params.models import Roots, Biomass
from agrogame.soil.models import SoilLayer, SoilProfile


# ---------------------------------------------------------------------------
# Roots validation (lines 37, 40)
# ---------------------------------------------------------------------------


def test_roots_distribution_not_summing_to_one() -> None:
    """Cover lines 37-40: distribution must sum to 1.0."""
    with pytest.raises(ValueError, match="distribution must sum to 1.0"):
        Roots(
            max_depth_cm=100.0,
            growth_rate_cm_per_day=1.0,
            distribution=[0.5, 0.3, 0.3],  # sum=1.1
        )


# ---------------------------------------------------------------------------
# Biomass validation (lines 69, 74, 76)
# ---------------------------------------------------------------------------


def test_biomass_harvest_index_out_of_range() -> None:
    """Cover line 69: harvest_index must be in (0, 1]."""
    with pytest.raises(ValueError, match="harvest_index must be in"):
        Biomass(
            rue_g_per_mj=3.0,
            harvest_index=1.5,
            partition_vegetative={"leaf": 1.0},
            partition_reproductive={"grain": 1.0},
        )


def test_biomass_partition_not_summing_to_one() -> None:
    """Cover line 74: partition must sum to 1.0."""
    with pytest.raises(ValueError, match="must sum to 1.0"):
        Biomass(
            rue_g_per_mj=3.0,
            harvest_index=0.5,
            partition_vegetative={"leaf": 0.5, "stem": 0.3},  # sum=0.8
            partition_reproductive={"grain": 1.0},
        )


def test_biomass_partition_negative_fraction() -> None:
    """Cover line 76: negative fractions not allowed."""
    with pytest.raises(ValueError, match="must not contain negative"):
        Biomass(
            rue_g_per_mj=3.0,
            harvest_index=0.5,
            partition_vegetative={"leaf": 1.5, "stem": -0.5},  # sum=1.0 but negative
            partition_reproductive={"grain": 1.0},
        )


# ---------------------------------------------------------------------------
# SoilLayer validation (lines 52, 56)
# ---------------------------------------------------------------------------


def test_soil_layer_water_bounds_violation() -> None:
    """Cover line 52: wilting_point >= field_capacity."""
    with pytest.raises(ValueError, match="wilting_point"):
        SoilLayer(
            depth_cm=30.0,
            texture="loam",
            field_capacity=0.25,
            wilting_point=0.30,  # violation: wp >= fc
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=10.0,
            organic_matter_pct=2.0,
            initial_no3_kg_ha=5.0,
            initial_nh4_kg_ha=2.0,
            initial_p_kg_ha=10.0,
        )


def test_soil_layer_negative_organic_matter() -> None:
    """Cover line 56: organic_matter_pct must be >= 0."""
    with pytest.raises(ValueError, match="organic_matter_pct"):
        SoilLayer(
            depth_cm=30.0,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.15,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=10.0,
            organic_matter_pct=-1.0,
            initial_no3_kg_ha=5.0,
            initial_nh4_kg_ha=2.0,
            initial_p_kg_ha=10.0,
        )


# ---------------------------------------------------------------------------
# SoilProfile validation (line 70)
# ---------------------------------------------------------------------------


def test_soil_profile_insufficient_depth() -> None:
    """Cover line 70: total depth must be at least 100 cm."""
    layers = [
        SoilLayer(
            depth_cm=10.0,
            texture="loam",
            field_capacity=0.30,
            wilting_point=0.15,
            saturation=0.45,
            bulk_density_g_cm3=1.3,
            ksat_mm_per_hour=10.0,
            organic_matter_pct=2.0,
            initial_no3_kg_ha=5.0,
            initial_nh4_kg_ha=2.0,
            initial_p_kg_ha=10.0,
        )
        for _ in range(3)
    ]
    with pytest.raises(ValueError, match="Total profile depth must be at least 100 cm"):
        SoilProfile(name="shallow", layers=layers)
