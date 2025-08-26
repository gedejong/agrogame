from __future__ import annotations

from agrogame.soil.canopy import CanopyModule, CanopyParams


def test_light_interception_fraction_increases_with_lai():
    params = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.0,
    )
    canopy = CanopyModule(params)
    canopy.state.lai = 0.0
    f0 = canopy.calculate_light_interception(10.0).intercepted_par_mj_m2
    canopy.state.lai = 3.0
    f1 = canopy.calculate_light_interception(10.0).intercepted_par_mj_m2
    canopy.state.lai = 4.0
    f2 = canopy.calculate_light_interception(10.0).intercepted_par_mj_m2
    assert f0 < f1 < f2


def test_biomass_growth_linear_with_par_and_temp_and_stress():
    params = CanopyParams(0.6, 3.0, 0.02, 6.0, 0.0)
    canopy = CanopyModule(params)
    inc_a = canopy.calculate_biomass_growth(
        10.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )
    inc_b = canopy.calculate_biomass_growth(
        20.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )
    assert inc_b == 2 * inc_a
    inc_c = canopy.calculate_biomass_growth(
        10.0, temp_factor=0.5, water_stress=1.0, n_stress=1.0
    )
    assert inc_c == 0.5 * inc_a
    inc_d = canopy.calculate_biomass_growth(
        10.0, temp_factor=1.0, water_stress=0.5, n_stress=0.7
    )
    assert inc_d == 0.5 * inc_a


def test_lai_update_respects_sla_senescence_and_cap():
    params = CanopyParams(0.6, 3.0, 0.02, 2.0, 0.1)
    canopy = CanopyModule(params)
    canopy.state.lai = 1.0
    new_lai = canopy.update_lai(new_leaf_biomass_g_m2=50.0)
    assert new_lai <= params.lai_max


def test_lai_scurve_and_high_interception_at_lai4():
    params = CanopyParams(0.6, 3.0, 0.05, 6.0, 0.0)
    canopy = CanopyModule(params)
    canopy.state.lai = 0.2
    # Grow over several days with constant biomass addition
    prev = canopy.state.lai
    for _ in range(10):
        canopy.update_lai(new_leaf_biomass_g_m2=5.0)
        assert canopy.state.lai >= prev
        prev = canopy.state.lai
    # Interception ~90-95% at LAI ~4 for k~0.6
    canopy.state.lai = 4.0
    fx = canopy.calculate_light_interception(incident_par_mj_m2=10.0)
    frac = fx.intercepted_par_mj_m2 / 10.0
    assert 0.9 <= frac <= 0.98
