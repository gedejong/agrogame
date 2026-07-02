"""Dual-porosity water flow model (#213).

MACRO/RZWQM-style simplified dual-domain approach. Partitions incoming
water between matrix flow (slow, via cascading bucket) and macropore
bypass flow (fast, instant gravity routing) based on rainfall intensity
vs matrix infiltration capacity. First-order exchange transfers water
between domains per day.

This is NOT a dual-Richards PDE solver — the daily timestep and bucket
cascade make full PDE inappropriate. Intensity-based partitioning,
instant macropore routing, and a linear exchange term capture the key
behavior at acceptable fidelity.

Refs:
    Jarvis, N.J. 2007. A review of non-equilibrium water flow and solute
        transport in soil macropores. Eur. J. Soil Sci. 58: 523-546.
    Gerke & van Genuchten 1993. Water Resour. Res. 29(2): 305-319.
    Ahuja et al. 2000. RZWQM model documentation.
"""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.params.ports import SoilProfileView
from agrogame.soil.pore_network.state import PoreNetworkState
from agrogame.soil.water.events import PreferentialFlowOccurred
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.models.dual_porosity_exchange import compute_exchange_mm
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes


@dataclass(frozen=True)
class DualPorosityParams:
    """Parameters for dual-porosity water flow.

    Attributes:
        bypass_threshold_factor: Fraction of matrix Ksat below which no
            bypass occurs (rainfall intensity absorbed entirely by matrix).
            Ref: Jarvis 2007 — typical value 0.5–0.8.
        alpha_w_per_day: First-order macropore-matrix exchange coefficient
            (1/day). Ref: Gerke & van Genuchten 1993 — 0.01–1.0 for most
            soils; default reflects moderately structured loam.
        min_macro_frac_for_activation: Minimum macroporosity (m3/m3) below
            which bypass is disabled (poorly structured soil has no
            effective macropore network).
        max_bypass_fraction: Safety cap on bypass fraction to prevent
            unphysical 100% bypass in edge cases.
    """

    bypass_threshold_factor: float = 0.6
    alpha_w_per_day: float = 0.2
    min_macro_frac_for_activation: float = 0.03
    max_bypass_fraction: float = 0.95


def partition_flow(
    rainfall_mm: float,
    rainfall_intensity_mm_hr: float,
    matrix_ksat_mm_hr: float,
    macro_frac: float,
    params: DualPorosityParams,
) -> tuple[float, float]:
    """Split incoming rainfall into matrix and macropore bypass amounts.

    Returns (matrix_mm, bypass_mm). Both sum to rainfall_mm.

    Logic (MACRO-style, Jarvis 2007):
    - If macroporosity below activation threshold → 100% matrix.
    - If intensity <= ksat × threshold_factor → 100% matrix.
    - Else: bypass_fraction = (intensity - threshold) / intensity.

    Ref: Jarvis 2007, Eur. J. Soil Sci. 58 — Table 3 intensity
    thresholds and bypass fractions for structured soils.
    """
    if rainfall_mm <= 0.0:
        return 0.0, 0.0
    if macro_frac < params.min_macro_frac_for_activation:
        return rainfall_mm, 0.0
    if matrix_ksat_mm_hr <= 0.0:
        # Degenerate (impervious) matrix: most routes through macropores;
        # residual goes to matrix (will runoff via SCS). Sum = rainfall_mm.
        bypass_mm = rainfall_mm * params.max_bypass_fraction
        return rainfall_mm - bypass_mm, bypass_mm
    threshold = matrix_ksat_mm_hr * params.bypass_threshold_factor
    if rainfall_intensity_mm_hr <= threshold:
        return rainfall_mm, 0.0
    bypass_fraction = (rainfall_intensity_mm_hr - threshold) / rainfall_intensity_mm_hr
    bypass_fraction = min(bypass_fraction, params.max_bypass_fraction)
    bypass_mm = rainfall_mm * bypass_fraction
    matrix_mm = rainfall_mm - bypass_mm
    return matrix_mm, bypass_mm


class DualPorosityWaterModel(CascadingBucketWaterModel):
    """Dual-porosity water model layered on the cascading bucket.

    Matrix flow uses inherited cascading bucket logic unchanged.
    Macropore bypass flow is routed layer-by-layer up to macropore
    capacity from ``PoreNetworkState``, with overflow to deep drainage.
    First-order exchange transfers water between domains per day.

    The caller must ensure ``SoilWaterState.theta_macro`` is initialized
    (e.g., via ``state.enable_dual_porosity(n_layers)``) before calling
    ``update_daily``.
    """

    def __init__(
        self,
        params: DualPorosityParams,
        pore_state: PoreNetworkState,
        event_bus: EventBus | None = None,
    ) -> None:
        """Create the dual-porosity model.

        Args:
            params: Dual-porosity tuning parameters.
            pore_state: Shared reference to pore network state. Caller
                is responsible for computing/updating pore_state before
                each daily step.
            event_bus: Optional bus to emit water events on.
        """
        super().__init__(event_bus=event_bus)
        self._params = params
        self._pore_state = pore_state

    def update_daily(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        drivers: DailyDrivers,
        ksat_factors: list[float] | None = None,
        porosity_overrides: list[float] | None = None,
    ) -> WaterFluxes:
        """Run one daily dual-porosity step.

        Sequence:
        1. Partition rainfall between matrix and macropore domains.
        2. Matrix flow: run inherited cascading bucket on matrix share.
        3. Macropore flow: route bypass layer-by-layer, overflow to
           deep drainage.
        4. Exchange: apply first-order macro-matrix transfer.

        Mass conservation: matrix_in + macro_in == matrix_out + macro_out
        + storage_change, enforced to 1e-6 tolerance.
        """
        if state.theta_macro is None:
            raise ValueError(
                "DualPorosityWaterModel requires theta_macro initialized. "
                "Call state.enable_dual_porosity(n_layers) first."
            )
        if len(state.theta_macro) < len(profile.layers):
            raise ValueError(
                f"theta_macro has {len(state.theta_macro)} layers "
                f"but profile has {len(profile.layers)}"
            )

        # --- Storage before (total = matrix + macro) ---
        matrix_before = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )
        macro_before = self._macro_storage_mm(profile, state)

        # --- 1. Partition rainfall only (irrigation is low-intensity) ---
        # Irrigation is applied at controlled drip/sprinkler rates, well
        # below macropore bypass thresholds — treat as matrix-only input.
        intensity = (
            drivers.rainfall_intensity_mm_hr
            if drivers.rainfall_intensity_mm_hr is not None
            else drivers.rainfall_mm / 24.0
        )
        top_ksat = profile.layers[0].ksat_mm_per_hour
        top_macro_frac = self._pore_state.macro[0] if self._pore_state.macro else 0.0
        rain_matrix_mm, bypass_mm = partition_flow(
            drivers.rainfall_mm,
            intensity,
            top_ksat,
            top_macro_frac,
            self._params,
        )
        incoming = drivers.rainfall_mm + drivers.irrigation_mm

        # --- 2. Matrix flow via inherited cascade ---
        # Matrix capacity is reduced by macropore volume fraction to
        # avoid double-counting: pore network state already allocates
        # ``macro_frac`` of bulk volume to the macropore domain.
        effective_overrides = self._build_matrix_porosity_overrides(
            profile, porosity_overrides
        )
        matrix_drivers = DailyDrivers(
            rainfall_mm=rain_matrix_mm,
            irrigation_mm=drivers.irrigation_mm,
            evaporation_mm=drivers.evaporation_mm,
            rainfall_intensity_mm_hr=intensity,
        )
        matrix_fluxes = super().update_daily(
            profile, state, matrix_drivers, ksat_factors, effective_overrides
        )

        # --- 3. Macropore bypass routing ---
        macro_deep_drainage, macro_layer_indices = self._route_macropore(
            profile, state, bypass_mm
        )
        if bypass_mm > 1e-9 and self.event_bus is not None:
            bypass_fraction = bypass_mm / incoming if incoming > 0 else 0.0
            self.event_bus.emit(
                PreferentialFlowOccurred(
                    bypass_fraction=bypass_fraction,
                    bypass_mm=bypass_mm,
                    layer_indices=tuple(macro_layer_indices),
                )
            )

        # --- 4. Exchange term ---
        self._apply_exchange(profile, state)

        # --- Storage after ---
        matrix_after = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )
        macro_after = self._macro_storage_mm(profile, state)
        total_storage_change = (matrix_after - matrix_before) + (
            macro_after - macro_before
        )

        # Aggregate fluxes
        total_deep_drainage = matrix_fluxes.deep_drainage_mm + macro_deep_drainage
        return WaterFluxes(
            runoff_mm=matrix_fluxes.runoff_mm,
            deep_drainage_mm=total_deep_drainage,
            evap_mm=matrix_fluxes.evap_mm,
            storage_change_mm=total_storage_change,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _macro_storage_mm(
        self, profile: SoilProfileView, state: SoilWaterState
    ) -> float:
        """Total water stored in macropore domain across all layers (mm)."""
        if state.theta_macro is None:
            return 0.0
        total = 0.0
        for i, layer in enumerate(profile.layers):
            if i >= len(state.theta_macro):
                break
            total += state.theta_macro[i] * layer.depth_cm * 10.0
        return total

    def _route_macropore(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        bypass_mm: float,
    ) -> tuple[float, list[int]]:
        """Route bypass water through macropore domain, top-to-bottom.

        Fills each layer's macropore domain up to its volumetric
        capacity (``pore_state.macro[i] * depth_mm``). Overflow cascades
        to the next layer, then to deep drainage at the profile bottom.

        Returns (deep_drainage_mm, filled_layer_indices).
        """
        if bypass_mm <= 0.0 or state.theta_macro is None:
            return 0.0, []
        remaining = bypass_mm
        filled: list[int] = []
        n = min(
            len(profile.layers), len(state.theta_macro), len(self._pore_state.macro)
        )
        for i in range(n):
            layer = profile.layers[i]
            depth_mm = layer.depth_cm * 10.0
            macro_cap_mm = self._pore_state.macro[i] * depth_mm
            current_mm = state.theta_macro[i] * depth_mm
            room_mm = max(0.0, macro_cap_mm - current_mm)
            added = min(room_mm, remaining)
            if added > 0.0:
                state.theta_macro[i] = (current_mm + added) / depth_mm
                filled.append(i)
            remaining -= added
            if remaining <= 1e-9:
                break
        # Any leftover (including when profile is fully filled) goes to
        # deep drainage — macropores vent rapidly to below the profile.
        return remaining, filled

    def _build_matrix_porosity_overrides(
        self,
        profile: SoilProfileView,
        porosity_overrides: list[float] | None,
    ) -> list[float]:
        """Per-layer effective matrix porosity = saturation - macro_frac.

        Prevents double-counting: pore network already reserves
        ``macro_frac`` of bulk soil volume for the macropore domain, so
        the matrix domain cascading bucket must cap at the remainder.
        """
        n = len(profile.layers)
        overrides: list[float] = []
        for i, layer in enumerate(profile.layers):
            base = (
                porosity_overrides[i]
                if porosity_overrides is not None and i < len(porosity_overrides)
                else layer.saturation
            )
            macro = (
                self._pore_state.macro[i] if i < len(self._pore_state.macro) else 0.0
            )
            overrides.append(max(0.0, base - macro))
        assert len(overrides) == n
        return overrides

    def _apply_exchange(self, profile: SoilProfileView, state: SoilWaterState) -> None:
        """Apply first-order macropore-matrix exchange per layer.

        Uses actual transferable amount (min of requested and available
        in source/sink) to avoid floating-point drift creating or
        destroying water via independent clamps in the setters.
        """
        if state.theta_macro is None:
            return
        n = min(
            len(profile.layers), len(state.theta_macro), len(self._pore_state.macro)
        )
        if n == 0:
            return
        exchanges = compute_exchange_mm(
            state.theta_macro[:n],
            state.theta[:n],
            profile,
            self._params.alpha_w_per_day,
            self._pore_state.macro[:n],
        )
        for i, q_ex_mm in enumerate(exchanges):
            if abs(q_ex_mm) < 1e-12:
                continue
            layer = profile.layers[i]
            depth_mm = layer.depth_cm * 10.0
            macro_stored_mm = state.theta_macro[i] * depth_mm
            matrix_stored_mm = state.layer_storage_mm(profile, i)
            # Matrix cap = saturation - macro_frac (double-count guard).
            macro_frac = self._pore_state.macro[i]
            matrix_cap_mm = max(0.0, (layer.saturation - macro_frac) * depth_mm)
            matrix_room_mm = max(0.0, matrix_cap_mm - matrix_stored_mm)
            if q_ex_mm > 0.0:
                # Macro → matrix; actual = min(requested, source, sink-room).
                actual = min(q_ex_mm, macro_stored_mm, matrix_room_mm)
            else:
                # Matrix → macro; actual = -min(requested, matrix-above-wp, macro-room).
                matrix_above_wp = max(
                    0.0, matrix_stored_mm - layer.wilting_point * depth_mm
                )
                macro_room = max(0.0, macro_frac * depth_mm - macro_stored_mm)
                actual = -min(-q_ex_mm, matrix_above_wp, macro_room)
            if actual == 0.0:
                continue
            macro_new_mm = macro_stored_mm - actual
            matrix_new_mm = matrix_stored_mm + actual
            state.theta_macro[i] = max(0.0, macro_new_mm / depth_mm)
            state.set_layer_storage_mm(profile, i, matrix_new_mm)
