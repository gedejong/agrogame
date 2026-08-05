from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.soil.phenology import PhenologyStage, StageChanged
from agrogame.soil.canopy.events import Harvested
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
    # Interception ~90-95% at LAI ~4 for k~0.6. The argument is incident
    # shortwave (ADR-014); the canopy converts to PAR via f_PAR=0.48 before
    # Beer-Lambert, so the interception fraction is measured against incident
    # PAR (0.48 * 10.0), not raw shortwave.
    canopy.state.lai = 4.0
    fx = canopy.calculate_light_interception(incident_shortwave_mj_m2=10.0)
    frac = fx.intercepted_par_mj_m2 / (0.48 * 10.0)
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
        incident_shortwave_mj_m2=12.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
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
        incident_shortwave_mj_m2=12.0,
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
        incident_shortwave_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=0.15,
    )
    high = _fresh_canopy_with_lai().daily_step(
        incident_shortwave_mj_m2=12.0,
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
        incident_shortwave_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=1.5,
    )
    assert over.biomass_increment_g_m2 == 0.0  # clamped to 1.0 → all to root
    assert over.root_increment_g_m2 > 0.0
    under = _fresh_canopy_with_lai().daily_step(
        incident_shortwave_mj_m2=12.0,
        temp_factor=1.0,
        water_stress=1.0,
        n_stress=1.0,
        root_allocation_fraction=-0.5,
    )
    assert under.root_increment_g_m2 == 0.0  # clamped to 0.0 → all to shoot
    assert under.biomass_increment_g_m2 > 0.0


# --- #433: net canopy growth gated at physiological maturity -----------------


def _canopy_with_bus(lai: float = 3.0) -> tuple[CanopyModule, EventBus]:
    bus = EventBus()
    params = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.05,  # non-zero so LAI still dies back
    )
    canopy = CanopyModule(params, event_bus=bus)
    canopy.state.lai = lai
    return canopy, bus


def _advance_to(bus: EventBus, from_stage: PhenologyStage, to: PhenologyStage) -> None:
    bus.emit(StageChanged(from_stage=from_stage, to_stage=to, at_gdd=0.0))


def test_maturity_gates_net_biomass_growth() -> None:
    """A MATURITY-stage canopy with positive LAI adds no net biomass (#433).

    Once the crop reaches physiological maturity, net canopy assimilation is
    gated to zero (DSSAT/APSIM convention) even though the senescing canopy
    still intercepts PAR. LAI senescence is unaffected — the canopy still
    visibly dies back.
    """
    canopy, bus = _canopy_with_bus(lai=3.0)
    _advance_to(bus, PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY)
    assert canopy._current_stage == PhenologyStage.MATURITY

    biomass_before = canopy.state.biomass_g_m2 = 500.0
    lai_before = canopy.state.lai
    fx = canopy.daily_step(
        incident_par_mj_m2=18.0,  # PAR > 0
        temp_factor=1.0,
        water_stress=0.6,  # moderate stress, still > 0
        n_stress=1.0,
    )
    # Net biomass growth is gated to zero at maturity...
    assert fx.biomass_increment_g_m2 == 0.0
    assert fx.root_increment_g_m2 == 0.0
    assert abs(canopy.state.biomass_g_m2 - biomass_before) < 1e-12
    # ...but PAR is still intercepted (canopy is not dead)...
    assert fx.intercepted_par_mj_m2 > 0.0
    # ...and LAI senescence continues (canopy dies back).
    assert canopy.state.lai < lai_before


def test_maturity_gate_holds_over_multiple_days() -> None:
    """Biomass stays flat across many maturity days despite daily PAR (#433)."""
    canopy, bus = _canopy_with_bus(lai=4.0)
    _advance_to(bus, PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY)
    canopy.state.biomass_g_m2 = 800.0
    for _ in range(30):
        canopy.daily_step(
            incident_par_mj_m2=20.0, temp_factor=1.0, water_stress=0.5, n_stress=1.0
        )
    assert abs(canopy.state.biomass_g_m2 - 800.0) < 1e-9


def test_gate_rearms_each_cycle_after_harvest() -> None:
    """Across two plant→harvest cycles the gate re-arms each cycle (#433).

    Pre-maturity growth is normal, maturity growth is zero, harvest resets the
    canopy, and the second cycle grows normally again before maturity.
    """
    canopy, bus = _canopy_with_bus(lai=2.0)

    def _grow_one_day() -> float:
        before = canopy.state.biomass_g_m2
        canopy.daily_step(
            incident_par_mj_m2=16.0, temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        return canopy.state.biomass_g_m2 - before

    for cycle in range(2):
        # Vegetative: net growth is positive (gate disarmed).
        _advance_to(bus, PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE)
        canopy.state.lai = max(canopy.state.lai, 2.0)
        assert _grow_one_day() > 0.0, f"cycle {cycle}: expected growth pre-maturity"
        # Maturity: net growth gated to zero.
        _advance_to(bus, PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY)
        assert _grow_one_day() == 0.0, f"cycle {cycle}: expected no growth at maturity"
        # Harvest resets the canopy for the next cycle.
        bus.emit(Harvested(fraction_remaining=0.0))
        assert canopy.state.biomass_g_m2 == 0.0
