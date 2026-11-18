from __future__ import annotations

from itertools import pairwise

import pytest

from agrogame.soil.microbes.responses import EnvironmentalResponses


def test_temperature_modifier_shape_bounds_and_optimum() -> None:
    resp = EnvironmentalResponses()
    # bounds
    for t in (-10.0, 0.0, 45.0, 60.0):
        v = resp.temperature_modifier(t)
        assert 0.0 <= v <= 1.0
        if t <= resp.temp_min_c or t >= resp.temp_max_c:
            assert v == 0.0
    # rising to optimum, then falling
    t_mid = (resp.temp_min_c + resp.temp_opt_c) / 2.0
    assert resp.temperature_modifier(t_mid) < resp.temperature_modifier(resp.temp_opt_c)
    t_after = (resp.temp_opt_c + resp.temp_max_c) / 2.0
    assert resp.temperature_modifier(t_after) < resp.temperature_modifier(
        resp.temp_opt_c
    )


def test_moisture_modifier_shape_bounds_and_optimum() -> None:
    resp = EnvironmentalResponses()
    for w in (-0.1, 0.0, 1.0, 1.1):
        v = resp.moisture_modifier(w)
        assert 0.0 <= v <= 1.0
        if w <= 0.0 or w >= 1.0:
            assert v == 0.0
    w_before = resp.moisture_opt_wfps / 2.0
    w_after = (1.0 + resp.moisture_opt_wfps) / 2.0
    assert resp.moisture_modifier(w_before) < resp.moisture_modifier(
        resp.moisture_opt_wfps
    )
    assert resp.moisture_modifier(w_after) < resp.moisture_modifier(
        resp.moisture_opt_wfps
    )


def test_ph_modifier_shape_bounds_and_optimum() -> None:
    """Rousk, Brookes & Bååth 2009 (doi:10.1128/aem.02775-08) response, #553 P0-2.

    1.0 at pH >= 6.8, linear to 2/3 at 4.5, linear to 0 at 4.0, 0 below.
    """
    resp = EnvironmentalResponses()
    # P0-2 points
    assert resp.ph_modifier(8.3) == 1.0
    assert resp.ph_modifier(6.8) == 1.0
    assert 0.70 <= resp.ph_modifier(5.0) <= 0.80
    assert resp.ph_modifier(4.5) == pytest.approx(2.0 / 3.0, abs=1e-9)
    assert resp.ph_modifier(4.0) == 0.0
    # Plateau above 6.8, zero below 4.0
    for ph in (6.9, 7.5, 9.0, 14.0):
        assert resp.ph_modifier(ph) == 1.0
    for ph in (3.99, 3.0, 0.0):
        assert resp.ph_modifier(ph) == 0.0
    # Linear segments: midpoints sit halfway between the knot values
    assert resp.ph_modifier(5.65) == pytest.approx(5.0 / 6.0, abs=1e-9)
    assert resp.ph_modifier(4.25) == pytest.approx(1.0 / 3.0, abs=1e-9)
    # Continuous, bounded and monotone non-decreasing across 3.0..9.0
    grid = [3.0 + 0.01 * i for i in range(601)]
    values = [resp.ph_modifier(ph) for ph in grid]
    assert all(0.0 <= v <= 1.0 for v in values)
    assert all(b >= a for a, b in pairwise(values))
    assert max(b - a for a, b in pairwise(values)) < 0.02


@pytest.mark.parametrize("bad_ph", [float("nan"), float("inf"), float("-inf")])
def test_ph_modifier_rejects_non_finite_ph(bad_ph: float) -> None:
    """A non-finite pH raises instead of silently zeroing microbial activity."""
    with pytest.raises(ValueError, match="finite"):
        EnvironmentalResponses().ph_modifier(bad_ph)
