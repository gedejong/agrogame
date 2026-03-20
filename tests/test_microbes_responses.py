from __future__ import annotations


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
    resp = EnvironmentalResponses()
    # bounds
    for ph in (
        resp.ph_opt - 5.0,
        resp.ph_opt - resp.ph_width,
        resp.ph_opt + resp.ph_width,
        resp.ph_opt + 5.0,
    ):
        v = resp.ph_modifier(ph)
        assert 0.0 <= v <= 1.0
        if abs(ph - resp.ph_opt) >= resp.ph_width:
            assert v == 0.0
    # peak at ph_opt
    mid_low = resp.ph_opt - resp.ph_width / 2.0
    mid_high = resp.ph_opt + resp.ph_width / 2.0
    peak = resp.ph_modifier(resp.ph_opt)
    assert resp.ph_modifier(mid_low) < peak
    assert resp.ph_modifier(mid_high) < peak
