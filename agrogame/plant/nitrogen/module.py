from __future__ import annotations

from .params import PlantNitrogenParams
from .state import PlantNitrogenState

# 1 g/m² of dry matter = 10 kg/ha (10,000 m² per ha).
_G_M2_TO_KG_HA = 10.0
# Below this shoot DM the plant is treated as an unstressed seedling: the
# stock/biomass ratio is numerically ill-conditioned and the dilution curve
# is not defined for a near-zero canopy.
_MIN_SHOOT_DM_KG_HA = 1.0  # 0.1 g/m²


class PlantNitrogenModule:
    """Whole-shoot critical-N dilution logic (#360).

    Pure calculator: owns the frozen :class:`PlantNitrogenParams` and
    operates on a mutable :class:`PlantNitrogenState`. Holds no event bus.

    The model accumulates the (unchanged, mass-flow-limited) soil N uptake
    into a whole-shoot N stock, converts it to an actual shoot N
    concentration, compares against the critical-N dilution curve to get the
    N nutrition index (NNI), and maps NNI to a continuous growth-stress
    factor. Gradedness comes from NNI being continuous — the canopy keeps its
    Liebig ``min()``.
    """

    def __init__(self, params: PlantNitrogenParams) -> None:
        self.params = params

    def critical_n_pct(self, shoot_dm_t_ha: float) -> float:
        """Critical shoot N concentration (% of DM) for a given shoot DM.

        ``N_crit% = a * W^-b`` (Lemaire & Gastal 1997). The power law is only
        valid above ``reference_biomass_t_ha`` (~1 t/ha), so below it the
        value is held flat at the reference (avoids the W -> 0 divergence).
        """
        p = self.params
        w = max(float(shoot_dm_t_ha), p.reference_biomass_t_ha)
        return float(p.n_crit_a * w ** (-p.n_crit_b))

    @staticmethod
    def actual_n_pct(n_stock_kg_ha: float, shoot_dm_kg_ha: float) -> float:
        """Actual shoot N concentration (% of DM) from stock and shoot DM."""
        if shoot_dm_kg_ha <= _MIN_SHOOT_DM_KG_HA:
            return 0.0
        return 100.0 * max(0.0, n_stock_kg_ha) / shoot_dm_kg_ha

    def nutrition_index(self, n_stock_kg_ha: float, shoot_dm_g_m2: float) -> float:
        """N nutrition index NNI = actual N% / critical N%.

        Returns 1.0 (unstressed) for a near-zero canopy where the ratio is
        ill-defined. NNI is *not* capped here; the luxury cap (NNI > 1) is
        applied in :meth:`stress_from_nni`.
        """
        shoot_dm_kg_ha = max(0.0, float(shoot_dm_g_m2)) * _G_M2_TO_KG_HA
        if shoot_dm_kg_ha <= _MIN_SHOOT_DM_KG_HA:
            return 1.0
        shoot_dm_t_ha = shoot_dm_kg_ha / 1000.0
        crit = self.critical_n_pct(shoot_dm_t_ha)
        if crit <= 0.0:
            return 1.0
        return self.actual_n_pct(n_stock_kg_ha, shoot_dm_kg_ha) / crit

    def demand_to_critical(
        self, shoot_dm_g_m2: float, current_stock_kg_ha: float
    ) -> float:
        """N (kg/ha) needed to bring the shoot stock up to critical N.

        The stock-based crop N demand (DSSAT CERES / APSIM): the deficit
        between the current stock and the critical-N target for today's
        shoot DM. Because the target tracks the (diluting) critical curve as
        the canopy grows, this naturally rolls today's growth demand together
        with recovery of any accumulated deficit. Returns 0 for a near-zero
        canopy. Actual uptake stays mass-flow (soil-supply) limited downstream.
        """
        shoot_dm_kg_ha = max(0.0, float(shoot_dm_g_m2)) * _G_M2_TO_KG_HA
        if shoot_dm_kg_ha <= _MIN_SHOOT_DM_KG_HA:
            return 0.0
        crit = self.critical_n_pct(shoot_dm_kg_ha / 1000.0)
        target_stock = shoot_dm_kg_ha * crit / 100.0
        return max(0.0, target_stock - max(0.0, float(current_stock_kg_ha)))

    def stress_from_nni(self, nni: float) -> float:
        """Map NNI to a growth-stress factor in [stress_floor, 1].

        Documented mapping: a linear rescale of NNI between
        ``nni_stress_min`` (-> ``stress_floor``) and ``nni_stress_ref``
        (-> 1.0), clamped. Luxury uptake (NNI > ``nni_stress_ref``) is capped
        at 1.0 — no growth bonus. With the default parameters
        (min=0, ref=1, floor=0) this is exactly ``clamp(NNI, 0..1)`` as in
        the issue AC; the anchors exist as a documented calibration lever
        (CERES-Maize NFAC style; Jones et al. 2003).
        """
        p = self.params
        span = p.nni_stress_ref - p.nni_stress_min
        scaled = (float(nni) - p.nni_stress_min) / span
        return max(p.stress_floor, min(1.0, scaled))

    def daily_step(
        self,
        state: PlantNitrogenState,
        uptake_kg_ha: float,
        shoot_dm_g_m2: float,
    ) -> float:
        """Accumulate today's uptake into the stock and return N stress.

        Mutates ``state`` with the new stock and the day's diagnostics
        (actual/critical N%, NNI, stress) and returns the stress factor.
        """
        state.n_stock_kg_ha += max(0.0, float(uptake_kg_ha))
        shoot_dm_kg_ha = max(0.0, float(shoot_dm_g_m2)) * _G_M2_TO_KG_HA
        state.actual_n_pct = self.actual_n_pct(state.n_stock_kg_ha, shoot_dm_kg_ha)
        state.critical_n_pct = self.critical_n_pct(shoot_dm_kg_ha / 1000.0)
        state.nni = self.nutrition_index(state.n_stock_kg_ha, shoot_dm_g_m2)
        state.stress = self.stress_from_nni(state.nni)
        return state.stress
