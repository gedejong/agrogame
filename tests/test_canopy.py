from __future__ import annotations

from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.plant.stress import compute_water_stress


def test_light_interception_fraction_increases_with_lai() -> None:
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


def test_biomass_growth_linear_with_par_and_temp_and_stress() -> None:
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


def test_lai_update_respects_sla_senescence_and_cap() -> None:
    params = CanopyParams(0.6, 3.0, 0.02, 2.0, 0.1)
    canopy = CanopyModule(params)
    canopy.state.lai = 1.0
    new_lai = canopy.update_lai(new_leaf_biomass_g_m2=50.0)
    assert new_lai <= params.lai_max


def test_lai_scurve_and_high_interception_at_lai4() -> None:
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


def test_compute_water_stress_monotonic() -> None:
    s1 = compute_water_stress(
        actual_transpiration_mm=1.0, potential_transpiration_mm=4.0
    )
    s2 = compute_water_stress(
        actual_transpiration_mm=2.0, potential_transpiration_mm=4.0
    )
    s3 = compute_water_stress(
        actual_transpiration_mm=4.0, potential_transpiration_mm=4.0
    )
    assert 0.0 <= s1 <= s2 <= s3 <= 1.0


# --- #337: single-pool competitive root/shoot partitioning ------------------


def _fresh_canopy_with_lai(lai: float = 3.0) -> CanopyModule:
    params = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.0,
    )
    canopy = CanopyModule(params)
    canopy.state.lai = lai
    return canopy


def test_root_allocation_default_zero_is_shoot_only() -> None:
    """Default fraction 0.0 reproduces pre-#337 shoot-only behaviour."""
    canopy = _fresh_canopy_with_lai()
    fx = canopy.daily_step(
        incident_par_mj_m2=12.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )
    assert fx.root_increment_g_m2 == 0.0
    # Whole pool went to shoot.
    assert canopy.state.biomass_g_m2 == fx.biomass_increment_g_m2 > 0.0


def test_daily_pool_conserved_shoot_plus_root_equals_gross() -> None:
    """Shoot + root shares sum to the day's gross assimilate (Σ = 1, #337).

    Roots draw from the same finite pool, so they never inflate total NPP.
    """
    ref = _fresh_canopy_with_lai()
    intercepted = ref.calculate_light_interception(12.0).intercepted_par_mj_m2
    gross = ref.calculate_biomass_growth(
        intercepted, temp_factor=1.0, water_stress=1.0, n_stress=1.0
    )
    canopy = _fresh_canopy_with_lai()
    fx = canopy.daily_step(
        incident_par_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=0.25,
    )
    assert abs((fx.biomass_increment_g_m2 + fx.root_increment_g_m2) - gross) < 1e-9
    assert abs(fx.root_increment_g_m2 - 0.25 * gross) < 1e-9
    assert abs(fx.biomass_increment_g_m2 - 0.75 * gross) < 1e-9
    # Shoot biomass grew by only the shoot share, not the whole pool.
    assert abs(canopy.state.biomass_g_m2 - 0.75 * gross) < 1e-9


def test_higher_root_fraction_lowers_shoot_same_total_pool() -> None:
    """A higher root fraction reduces the shoot increment (true tradeoff).

    The total pool (shoot + root) is identical for both fractions on the same
    day — allocating more below ground does not create free biomass (#337).
    """
    low = _fresh_canopy_with_lai().daily_step(
        incident_par_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=0.15,
    )
    high = _fresh_canopy_with_lai().daily_step(
        incident_par_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=0.30,
    )
    assert high.biomass_increment_g_m2 < low.biomass_increment_g_m2
    assert high.root_increment_g_m2 > low.root_increment_g_m2
    low_total = low.biomass_increment_g_m2 + low.root_increment_g_m2
    high_total = high.biomass_increment_g_m2 + high.root_increment_g_m2
    assert abs(low_total - high_total) < 1e-9


def test_root_fraction_clamped_to_unit_interval() -> None:
    """Out-of-range fractions clamp so shoot/root shares stay non-negative."""
    over = _fresh_canopy_with_lai().daily_step(
        incident_par_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=1.5,
    )
    assert over.biomass_increment_g_m2 == 0.0  # clamped to 1.0 → all to root
    assert over.root_increment_g_m2 > 0.0
    under = _fresh_canopy_with_lai().daily_step(
        incident_par_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=-0.5,
    )
    assert under.root_increment_g_m2 == 0.0  # clamped to 0.0 → all to shoot
    assert under.biomass_increment_g_m2 > 0.0
