# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import math

from agrogame.plant.stress import StressCalculator, compute_water_stress


def test_compute_water_stress_basic() -> None:
    assert compute_water_stress(0.0, 0.0) == 1.0
    assert compute_water_stress(0.0, 1.0) == 0.0
    assert math.isclose(compute_water_stress(0.5, 1.0), 0.5)
    assert compute_water_stress(2.0, 1.0) == 1.0


def test_stress_calculator_combine_methods() -> None:
    calc = StressCalculator("liebig")
    assert calc.combine(0.7, 0.9, 0.8) == 0.7
    calc2 = StressCalculator("multiplicative")
    assert math.isclose(calc2.combine(0.7, 0.9, 0.8), 0.7 * 0.9 * 0.8)


def test_nutrient_from_uptake_demand() -> None:
    calc = StressCalculator()
    assert calc.nutrient_from_uptake_demand(0.0, 0.0) == 1.0
    assert calc.nutrient_from_uptake_demand(0.0, 2.0) == 0.0
    assert math.isclose(calc.nutrient_from_uptake_demand(1.0, 2.0), 0.5)
    assert calc.nutrient_from_uptake_demand(3.0, 2.0) == 1.0


def test_nutrient_from_concentration_piecewise() -> None:
    calc = StressCalculator()
    # Below critical -> 0
    assert (
        calc.nutrient_from_concentration(1.0, optimal_conc=3.0, critical_conc=2.0)
        == 0.0
    )
    # Above optimal -> 1
    assert (
        calc.nutrient_from_concentration(4.0, optimal_conc=3.0, critical_conc=2.0)
        == 1.0
    )
    # Linear between 2 and 3
    assert math.isclose(calc.nutrient_from_concentration(2.5, 3.0, 2.0), 0.5)
