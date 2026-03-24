"""Tests covering missing lines in agrogame/sim/builder.py."""

from __future__ import annotations

from agrogame.sim.builder import generate_rain_evap, generate_temp_par


# ---------------------------------------------------------------------------
# generate_rain_evap patterns (lines 38-42 seasonal, storms)
# ---------------------------------------------------------------------------


def test_generate_rain_evap_seasonal() -> None:
    """Cover lines 38-42: seasonal pattern."""
    rains, evaps = generate_rain_evap(30, 5.0, 3.0, pattern="seasonal")
    assert len(rains) == 30
    assert len(evaps) == 30
    # Should vary (not all equal)
    assert max(rains) > min(rains)


def test_generate_rain_evap_storms() -> None:
    """Cover storms pattern branch."""
    rains, evaps = generate_rain_evap(14, 5.0, 3.0, pattern="storms")
    assert len(rains) == 14
    # Storm spikes every 7 days
    assert rains[0] > rains[1]


# ---------------------------------------------------------------------------
# generate_temp_par seasonal pattern (lines 81-83)
# ---------------------------------------------------------------------------


def test_generate_temp_par_seasonal() -> None:
    """Cover lines 81-83: seasonal pattern."""
    tmins, tmaxs, pars = generate_temp_par(30, 10.0, 25.0, 12.0, pattern="seasonal")
    assert len(tmins) == 30
    assert max(tmins) > min(tmins)


def test_generate_temp_par_constant() -> None:
    """Cover constant/default pattern."""
    tmins, tmaxs, pars = generate_temp_par(10, 10.0, 25.0, 12.0)
    assert all(t == 10.0 for t in tmins)
    assert all(t == 25.0 for t in tmaxs)
