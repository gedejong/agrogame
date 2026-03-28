"""Three-pool SOM decomposition module (RothC/Century-inspired).

Decomposes soil organic matter through labile, intermediate, and stable pools
with temperature- and moisture-dependent kinetics, humification transfers,
and coupled C-N cycling.

References:
    Coleman & Jenkinson (1996) — RothC-26.3 model description.
    Parton et al. (1987) — Century model.
    Linn & Doran (1984) — Aerobic/anaerobic moisture response.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.soil.models import SoilProfile


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SOMPoolParams:
    """Pool-specific decomposition parameters (RothC-inspired defaults)."""

    # Decomposition rates (1/day)
    k_labile: float = 0.05  # ~20 d turnover at 25 °C
    k_intermediate: float = 0.001  # ~3 yr turnover
    k_stable: float = 0.00005  # ~55 yr turnover

    # Humification fractions (decomposed C transferred to next pool)
    humification_labile_to_inter: float = 0.3
    humification_inter_to_stable: float = 0.1

    # Microbial growth efficiency per pool
    mge_labile: float = 0.40
    mge_intermediate: float = 0.20
    mge_stable: float = 0.15

    # Priming and N cycling
    priming_max: float = 1.5  # max priming multiplier
    cn_critical: float = 25.0  # C:N above which N immobilization occurs

    # Aggregate protection (AGRO-104)
    # Base protected fractions (at 40% clay — scaled linearly by clay_pct)
    protection_frac_labile: float = 0.10  # 10% of labile protected
    protection_frac_intermediate: float = 0.40  # 40% of intermediate
    protection_frac_stable: float = 0.60  # 60% of stable
    protection_reduction: float = 0.70  # protected C decomposes 70% slower
    clay_protection_scale: float = 40.0  # clay% at which protection is 100%
    wet_dry_release_frac: float = 0.20  # fraction of protected released per event


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


@dataclass
class SOMLayerPool:
    """Per-pool C and N state for a single soil layer."""

    c_kg_ha: float = 0.0
    n_kg_ha: float = 0.0

    @property
    def cn_ratio(self) -> float:
        """Return C:N ratio, or 0.0 when N is non-positive."""
        if self.n_kg_ha <= 0.0:
            return 0.0
        return self.c_kg_ha / self.n_kg_ha


@dataclass
class SOMLayerState:
    """Aggregated SOM state for one soil layer (three pools)."""

    labile: SOMLayerPool = field(default_factory=SOMLayerPool)
    intermediate: SOMLayerPool = field(default_factory=SOMLayerPool)
    stable: SOMLayerPool = field(default_factory=SOMLayerPool)
    cumulative_co2_c_kg_ha: float = 0.0

    @property
    def total_c(self) -> float:
        return self.labile.c_kg_ha + self.intermediate.c_kg_ha + self.stable.c_kg_ha

    @property
    def total_n(self) -> float:
        return self.labile.n_kg_ha + self.intermediate.n_kg_ha + self.stable.n_kg_ha


@dataclass
class SOMState:
    """SOM state across all soil layers."""

    layers: list[SOMLayerState] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fluxes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SOMDailyFluxes:
    """Daily C and N fluxes returned by :meth:`ThreePoolSOM.daily_step`."""

    decomposed_c_kg_ha: float  # total C decomposed across pools
    co2_c_kg_ha: float  # C lost as CO2 respiration
    mineralized_n_kg_ha: float  # net N released (negative = immobilization)
    immobilized_n_kg_ha: float  # N drawn from mineral pool
    humified_c_kg_ha: float  # C transferred between pools
    microbial_c_kg_ha: float  # C allocated to microbial growth (MGE)


# ---------------------------------------------------------------------------
# Default C:N ratios for initialisation
# ---------------------------------------------------------------------------

_DEFAULT_CN_LABILE = 12.0
_DEFAULT_CN_INTERMEDIATE = 15.0
_DEFAULT_CN_STABLE = 20.0

# van Bemmelen factor: C = OM * 0.58
_VAN_BEMMELEN = 0.58

# Pool distribution of total OM-C at initialisation
_FRAC_LABILE = 0.05
_FRAC_INTERMEDIATE = 0.20
_FRAC_STABLE = 0.75


# ---------------------------------------------------------------------------
# Module
# ---------------------------------------------------------------------------


class ThreePoolSOM:
    """Three-pool soil organic matter decomposition module.

    Inspired by RothC (Coleman & Jenkinson 1996) and Century (Parton 1987).
    Tracks labile, intermediate, and stable C/N pools per soil layer with
    temperature, moisture, and C:N quality modifiers.
    """

    def __init__(self, params: SOMPoolParams, n_layers: int) -> None:
        if n_layers < 1:
            raise ValueError(f"n_layers must be >= 1, got {n_layers}")
        self.params = params
        self.state = SOMState(
            layers=[
                SOMLayerState(
                    labile=SOMLayerPool(),
                    intermediate=SOMLayerPool(),
                    stable=SOMLayerPool(),
                )
                for _ in range(n_layers)
            ]
        )

    # ------------------------------------------------------------------
    # Initialisation from soil profile
    # ------------------------------------------------------------------

    def initialize_from_profile(self, profile: SoilProfile) -> None:
        """Set initial pool sizes from soil organic matter percentage.

        Distribution: 5 % labile, 20 % intermediate, 75 % stable.
        C = OM × 0.58 (van Bemmelen factor).
        N derived from default C:N ratios (labile 12, intermediate 15, stable 20).

        The profile must have at least as many layers as ``self.state.layers``.
        """
        for i, layer_state in enumerate(self.state.layers):
            if i >= len(profile.layers):
                break
            soil_layer = profile.layers[i]

            # Total organic C in kg/ha (OM% → fraction, times depth and bulk density)
            # 1 ha = 10 000 m², depth in cm → m, density g/cm³ → kg/m³ (×1000)
            depth_m = soil_layer.depth_cm / 100.0
            bulk_kg_m3 = soil_layer.bulk_density_g_cm3 * 1000.0
            om_fraction = soil_layer.organic_matter_pct / 100.0
            total_om_kg_ha = om_fraction * bulk_kg_m3 * depth_m * 10_000.0
            total_c_kg_ha = total_om_kg_ha * _VAN_BEMMELEN

            c_lab = total_c_kg_ha * _FRAC_LABILE
            c_int = total_c_kg_ha * _FRAC_INTERMEDIATE
            c_stb = total_c_kg_ha * _FRAC_STABLE

            layer_state.labile.c_kg_ha = c_lab
            layer_state.labile.n_kg_ha = c_lab / _DEFAULT_CN_LABILE

            layer_state.intermediate.c_kg_ha = c_int
            layer_state.intermediate.n_kg_ha = c_int / _DEFAULT_CN_INTERMEDIATE

            layer_state.stable.c_kg_ha = c_stb
            layer_state.stable.n_kg_ha = c_stb / _DEFAULT_CN_STABLE

    # ------------------------------------------------------------------
    # Wet-dry disruption (Birch effect, AGRO-104)
    # ------------------------------------------------------------------

    def apply_wet_dry_disruption(self, layer_idx: int, intensity: float = 1.0) -> float:
        """Release protected SOM after a wet-dry cycle (Birch effect).

        Temporarily makes a fraction of aggregate-protected C available
        for decomposition by increasing pool C (simulating physical
        disruption of aggregates). Returns the total C released.

        Ref: Birch (1958) — flush of decomposition after rewetting.
        """
        if layer_idx < 0 or layer_idx >= len(self.state.layers):
            return 0.0
        layer = self.state.layers[layer_idx]
        release = self.params.wet_dry_release_frac * max(0.0, min(1.0, intensity))
        # Boost each pool's C by releasing "protected" fraction into decomposable
        # This is modeled as a temporary increase in effective pool size
        released_c = 0.0
        for pool in (layer.labile, layer.intermediate, layer.stable):
            boost = pool.c_kg_ha * release
            pool.c_kg_ha += boost
            released_c += boost
        return released_c

    # ------------------------------------------------------------------
    # Environmental modifiers
    # ------------------------------------------------------------------

    @staticmethod
    def _temperature_factor(temp_c: float) -> float:
        """Q10 = 2 temperature response centred on 25 °C (RothC)."""
        return float(2.0 ** ((temp_c - 25.0) / 10.0))

    @staticmethod
    def _moisture_factor(wfps: float) -> float:
        """Optimum at 60 % WFPS (Linn & Doran 1984)."""
        if wfps <= 0.0:
            return 0.0
        if wfps <= 0.6:
            return min(1.0, wfps / 0.6)
        return max(0.0, 1.0 - (wfps - 0.6) / 0.4)

    # ------------------------------------------------------------------
    # Per-pool decomposition helper
    # ------------------------------------------------------------------

    def _decompose_pool(
        self,
        pool: SOMLayerPool,
        k: float,
        mge: float,
        hum_frac: float,
        receiver: SOMLayerPool | None,
        env_f: float,
    ) -> tuple[float, float, float, float, float]:
        """Decompose a single pool. Returns 5-tuple of C/N fluxes."""
        if pool.c_kg_ha <= 0.0:
            return 0.0, 0.0, 0.0, 0.0, 0.0

        cn = pool.cn_ratio
        cn_qf = min(1.0, self.params.cn_critical / cn) if cn > 0 else 1.0

        decomposed_c = min(pool.c_kg_ha, pool.c_kg_ha * k * env_f * cn_qf)
        decomposed_n = min(pool.n_kg_ha, decomposed_c / cn) if cn > 0 else 0.0

        humified_c = decomposed_c * hum_frac
        microbial_c = decomposed_c * mge
        co2_c = max(0.0, decomposed_c - humified_c - microbial_c)

        pool.c_kg_ha -= decomposed_c
        pool.n_kg_ha -= decomposed_n

        if receiver is not None and humified_c > 0.0:
            receiver.c_kg_ha += humified_c
            receiver.n_kg_ha += decomposed_n * hum_frac

        return decomposed_c, co2_c, humified_c, microbial_c, decomposed_n

    # ------------------------------------------------------------------
    # Daily step
    # ------------------------------------------------------------------

    def _protection_factor(self, base_frac: float, clay_pct: float) -> float:
        """Compute effective protection rate reduction for a pool.

        Returns a multiplier in [1 - protection_reduction, 1.0] where
        1.0 = no protection (sand) and lower = more protection (clay).
        Ref: Six et al. (2002) — aggregate stabilization and clay content.
        """
        scale = min(1.0, clay_pct / self.params.clay_protection_scale)
        protected = base_frac * scale
        return 1.0 - protected * self.params.protection_reduction

    def daily_step(
        self,
        layer_idx: int,
        temp_c: float,
        wfps: float,
        priming_multiplier: float = 1.0,
        fresh_c_input: float = 0.0,
        fresh_n_input: float = 0.0,
        clay_pct: float = 22.0,
    ) -> SOMDailyFluxes:
        """Process one layer for one day.

        Args:
            layer_idx: Index into ``self.state.layers``.
            temp_c: Soil temperature (°C).
            wfps: Water-filled pore space (0–1).
            priming_multiplier: Rhizosphere priming factor (≥ 1).
            fresh_c_input: Fresh organic C added to labile pool (kg C/ha).
            fresh_n_input: Fresh organic N added to labile pool (kg N/ha).
            clay_pct: Clay content (%) for aggregate protection scaling.

        Returns:
            :class:`SOMDailyFluxes` with decomposition, respiration, and N fluxes.
        """
        if layer_idx < 0 or layer_idx >= len(self.state.layers):
            raise IndexError(
                f"layer_idx {layer_idx} out of range [0, {len(self.state.layers)})"
            )

        params = self.params
        layer = self.state.layers[layer_idx]

        temp_f = self._temperature_factor(temp_c)
        moist_f = self._moisture_factor(wfps)
        env_f = temp_f * moist_f

        priming = min(max(priming_multiplier, 1.0), params.priming_max)

        # --- Add fresh inputs to labile pool ---
        layer.labile.c_kg_ha += fresh_c_input
        layer.labile.n_kg_ha += fresh_n_input

        # Snapshot total C before decomposition (for mass-balance check)
        total_c_before = layer.total_c

        # --- Aggregate protection rate multipliers (AGRO-104) ---
        pf_lab = self._protection_factor(params.protection_frac_labile, clay_pct)
        pf_int = self._protection_factor(params.protection_frac_intermediate, clay_pct)
        pf_stb = self._protection_factor(params.protection_frac_stable, clay_pct)

        # --- Decompose each pool via helper ---
        pool_specs = [
            (
                layer.labile,
                params.k_labile * priming * pf_lab,
                params.mge_labile,
                params.humification_labile_to_inter,
                layer.intermediate,
            ),
            (
                layer.intermediate,
                params.k_intermediate * pf_int,
                params.mge_intermediate,
                params.humification_inter_to_stable,
                layer.stable,
            ),
            (layer.stable, params.k_stable * pf_stb, params.mge_stable, 0.0, None),
        ]

        total_decomposed_c = 0.0
        total_co2_c = 0.0
        total_humified_c = 0.0
        total_microbial_c = 0.0
        total_decomposed_n = 0.0

        for pool, k, mge, hum_frac, receiver in pool_specs:
            dc, co2, hum, mic, dn = self._decompose_pool(
                pool, k, mge, hum_frac, receiver, env_f
            )
            total_decomposed_c += dc
            total_co2_c += co2
            total_humified_c += hum
            total_microbial_c += mic
            total_decomposed_n += dn

        # --- N mineralisation / immobilization ---
        # N released from decomposition minus N retained in humified transfers
        net_mineralized_n = total_decomposed_n * (
            1.0 - params.humification_labile_to_inter
        )
        immobilized_n = 0.0

        if total_decomposed_c > 0.0 and total_decomposed_n > 0.0:
            effective_cn = total_decomposed_c / total_decomposed_n
            if effective_cn > params.cn_critical:
                # N deficit — need immobilization from mineral pool
                n_demand = total_decomposed_c / params.cn_critical
                n_deficit = n_demand - total_decomposed_n
                immobilized_n = max(0.0, n_deficit)
                net_mineralized_n = -immobilized_n

        # Update cumulative CO2
        layer.cumulative_co2_c_kg_ha += total_co2_c

        # --- Mass-balance check ---
        # C in = total_c_before + fresh inputs (already added)
        # C out = remaining pools + co2 + microbial (exported)
        total_c_after = layer.total_c
        c_accounted = total_c_after + total_co2_c + total_microbial_c
        if total_c_before > 0.0:
            balance_error = abs(c_accounted - total_c_before) / total_c_before
            if balance_error >= 0.001:
                raise ValueError(
                    f"SOM C mass-balance error: {balance_error:.4%} "
                    f"(before={total_c_before:.4f}, "
                    f"accounted={c_accounted:.4f})"
                )

        return SOMDailyFluxes(
            decomposed_c_kg_ha=total_decomposed_c,
            co2_c_kg_ha=total_co2_c,
            mineralized_n_kg_ha=net_mineralized_n,
            immobilized_n_kg_ha=immobilized_n,
            humified_c_kg_ha=total_humified_c,
            microbial_c_kg_ha=total_microbial_c,
        )
