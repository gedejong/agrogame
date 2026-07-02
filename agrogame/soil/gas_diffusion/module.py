"""Gas diffusion module — O2/CO2 transport through the soil pore network.

Solves the steady-state 1D Fick's second law per day-step using a
tridiagonal linear system (Thomas algorithm). Air-filled porosity and
Millington-Quirk tortuosity control the effective diffusivity per
layer; the O2 sink is driven by microbial respiration (previous day's
CO2 production, explicit lag to avoid circular dependency).

Refs:
    Millington, R.J. & Quirk, J.P. 1961. Permeability of porous solids.
        Trans. Faraday Soc. 57: 1200–1207. (τ = θ_a^(10/3) / φ²)
    Moldrup, P. et al. 2000. Predicting the gas diffusion coefficient
        in repacked soil. Soil Sci. Soc. Am. J. 64: 1588–1594.
    Massman, W.J. 1998. A review of the molecular diffusivities of H2O,
        CO2, CH4, CO, O3, SO2, NH3, N2O, NO, and NO2 in air, O2 and N2
        near STP. Atmos. Environ. 32: 1111–1127.
    Stepniewski, W. et al. 1994. Soil aeration — oxygen diffusion and
        biological indices. Adv. GeoEcol. 27: 195–218.

Orchestrator wiring (``GasDiffusionRuntime`` subscribing to CO2Respired
and DayTick) is deferred to a follow-up issue, matching the landing
order used in #211 and #213.
"""

from __future__ import annotations


from agrogame.events import EventBus
from agrogame.soil.gas_diffusion.events import GasConcentrationUpdated
from agrogame.soil.gas_diffusion.params import GasDiffusionParams
from agrogame.soil.gas_diffusion.state import GasDiffusionState
from agrogame.params.ports import SoilProfileView
from agrogame.soil.pore_network.state import PoreNetworkState

_EPS = 1e-12


def millington_quirk_tau(air_porosity: float, total_porosity: float) -> float:
    """Millington-Quirk 1961 tortuosity factor.

    τ = θ_a^(10/3) / φ²

    Returns 0 for degenerate inputs (non-positive porosity or air-filled
    porosity). Caller should treat τ=0 as "no diffusion in this layer".
    """
    if total_porosity <= _EPS or air_porosity <= 0.0:
        return 0.0
    return float((air_porosity ** (10.0 / 3.0)) / (total_porosity * total_porosity))


def temperature_corrected_d(
    d_ref_m2_per_s: float, temp_c: float, t_ref_k: float, exponent: float
) -> float:
    """Massman 1998 temperature scaling: D(T) = D_ref × (T/T_ref)^n."""
    t_k = max(1.0, temp_c + 273.15)
    return float(d_ref_m2_per_s * (t_k / t_ref_k) ** exponent)


def solve_tridiagonal(
    a: list[float], b: list[float], c: list[float], d: list[float]
) -> list[float]:
    """Thomas algorithm for a tridiagonal system (a·x_{i-1} + b·x_i + c·x_{i+1} = d).

    ``a[0]`` and ``c[-1]`` are unused (boundary rows absorb them).
    Raises ValueError on a zero pivot (singular or degenerate system).
    """
    n = len(b)
    if n == 0:
        return []
    if not (len(a) == n and len(c) == n and len(d) == n):
        raise ValueError("Tridiagonal vectors must all have length n")
    cp = [0.0] * n
    dp = [0.0] * n
    if abs(b[0]) < _EPS:
        raise ValueError("Tridiagonal solve: zero pivot at row 0")
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        denom = b[i] - a[i] * cp[i - 1]
        if abs(denom) < _EPS:
            raise ValueError(f"Tridiagonal solve: zero pivot at row {i}")
        cp[i] = c[i] / denom if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / denom
    x = [0.0] * n
    x[-1] = dp[-1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x


class GasDiffusionModule:
    """Compute steady-state O2 and CO2 profiles per soil layer."""

    def __init__(
        self,
        params: GasDiffusionParams,
        state: GasDiffusionState,
        event_bus: EventBus | None = None,
    ) -> None:
        self._params = params
        self._state = state
        self._bus = event_bus

    # -------- properties --------

    @property
    def state(self) -> GasDiffusionState:
        return self._state

    def set_state(self, state: GasDiffusionState) -> None:
        """Replace state contents in place to preserve aliases.

        See :meth:`PoreNetworkModule.set_state` for rationale — runtimes
        and the orchestrator hold the same state object identity and
        rely on it remaining stable across snapshot restore.
        """
        self._state.o2_frac = list(state.o2_frac)
        self._state.co2_frac = list(state.co2_frac)
        self._state.anaerobic = list(state.anaerobic)
        self._state.anaerobic_microsite_frac = list(state.anaerobic_microsite_frac)

    @property
    def params(self) -> GasDiffusionParams:
        return self._params

    # -------- main API --------

    def daily_step(
        self,
        profile: SoilProfileView,
        theta: list[float],
        temperature_c: float,
        co2_respiration_kg_c_ha: list[float],
        pore_state: PoreNetworkState | None = None,
    ) -> None:
        """Solve steady-state gas profile for one day.

        Args:
            profile: Soil profile (layer depths, saturation).
            theta: Volumetric water content per layer (m3/m3).
            temperature_c: Mean daily soil temperature (°C).
            co2_respiration_kg_c_ha: Previous day's CO2-C respiration
                per layer (kg C/ha/day). Drives O2 demand at
                respiratory_quotient mol O2 / mol CO2.
            pore_state: Optional refined pore geometry. When provided,
                total porosity per layer is the sum of macro+meso+micro
                +crypto fractions; otherwise ``SoilLayer.saturation``.
        """
        n = min(len(profile.layers), len(theta), len(self._state.o2_frac))
        if n == 0:
            return

        phi = self._total_porosity(profile, pore_state, n)
        theta_a = [max(0.0, phi[i] - theta[i]) for i in range(n)]
        d_o2_air = temperature_corrected_d(
            self._params.d_o2_air_ref_m2_per_s,
            temperature_c,
            self._params.t_ref_k,
            self._params.temp_exponent,
        )
        d_co2_air = temperature_corrected_d(
            self._params.d_co2_air_ref_m2_per_s,
            temperature_c,
            self._params.t_ref_k,
            self._params.temp_exponent,
        )
        tau = [millington_quirk_tau(theta_a[i], phi[i]) for i in range(n)]
        # Floor D_eff to avoid singular tridiagonal at saturation. Water-
        # phase diffusion is ~10^-4 × air-phase, so 1e-5 of D_air is a
        # physically defensible lower bound (Moldrup et al. 2000).
        d_floor_o2 = d_o2_air * 1e-5
        d_floor_co2 = d_co2_air * 1e-5
        d_eff_o2 = [max(d_floor_o2, d_o2_air * tau[i]) for i in range(n)]
        d_eff_co2 = [max(d_floor_co2, d_co2_air * tau[i]) for i in range(n)]

        # Convert CO2-C respiration (kg C/ha/day) → volumetric consumption
        # rate in the gas phase (fraction/s of the air-filled pore volume).
        o2_sink = self._compute_volumetric_rates(
            profile, theta_a, co2_respiration_kg_c_ha, n, kind="o2_sink"
        )
        co2_source = self._compute_volumetric_rates(
            profile, theta_a, co2_respiration_kg_c_ha, n, kind="co2_source"
        )

        # Solve O2 profile (top = atmospheric, bottom = zero-flux)
        self._state.o2_frac[:n] = self._solve_profile(
            profile,
            d_eff_o2,
            o2_sink,
            n,
            top_boundary=self._params.atmospheric_o2_frac,
            source_sign=-1.0,
        )
        # Solve CO2 profile (top = atmospheric, bottom = zero-flux, source term)
        self._state.co2_frac[:n] = self._solve_profile(
            profile,
            d_eff_co2,
            co2_source,
            n,
            top_boundary=self._params.atmospheric_co2_frac,
            source_sign=+1.0,
        )

        # Anaerobic flags and microsite fraction
        for i in range(n):
            below_o2 = self._state.o2_frac[i] < self._params.anaerobic_o2_threshold_frac
            below_porosity = theta_a[i] < self._params.critical_air_porosity
            self._state.anaerobic[i] = below_o2 or below_porosity
            self._state.anaerobic_microsite_frac[i] = self._microsite_fraction(
                self._state.o2_frac[i]
            )
            if self._bus is not None:
                self._bus.emit(
                    GasConcentrationUpdated(
                        layer=i,
                        o2_frac=self._state.o2_frac[i],
                        co2_frac=self._state.co2_frac[i],
                        anaerobic=self._state.anaerobic[i],
                        anaerobic_microsite_frac=(
                            self._state.anaerobic_microsite_frac[i]
                        ),
                    )
                )

    # -------- helpers --------

    def _total_porosity(
        self,
        profile: SoilProfileView,
        pore_state: PoreNetworkState | None,
        n: int,
    ) -> list[float]:
        """Layer porosity from ``pore_state`` if given, else ``saturation``."""
        out: list[float] = []
        for i in range(n):
            if pore_state is not None and i < len(pore_state.macro):
                out.append(pore_state.total_porosity(i))
            else:
                out.append(profile.layers[i].saturation)
        return out

    def _compute_volumetric_rates(
        self,
        profile: SoilProfileView,
        theta_a: list[float],
        co2_respiration_kg_c_ha: list[float],
        n: int,
        kind: str,
    ) -> list[float]:
        """Convert respiration (kg C/ha/day) → volumetric gas rate (1/s).

        kg C/ha/day → mol C/m3-air/s, then O2 sink = RQ × rate, CO2
        source = rate. Scaled by ``1 / theta_a`` (per unit air volume).
        """
        secs_per_day = 86400.0
        m2_per_ha = 1e4
        c_g_per_mol = 12.0
        rates: list[float] = []
        for i in range(n):
            rate_kg_c_per_ha_per_day = (
                co2_respiration_kg_c_ha[i] if i < len(co2_respiration_kg_c_ha) else 0.0
            )
            layer_depth_m = profile.layers[i].depth_cm / 100.0
            if theta_a[i] <= _EPS or layer_depth_m <= 0.0:
                rates.append(0.0)
                continue
            # kg C / (ha · day) → g / (m² · day) via ×1000 / (m²/ha)
            g_c_per_m2_per_day = rate_kg_c_per_ha_per_day * 1000.0 / m2_per_ha
            mol_c_per_m2_per_s = g_c_per_m2_per_day / c_g_per_mol / secs_per_day
            # Distributed uniformly through air-filled pore volume of the layer:
            # air volume per m2 soil = theta_a * depth_m
            mol_per_m3_air_per_s = mol_c_per_m2_per_s / (theta_a[i] * layer_depth_m)
            # Volume fraction rate = mol/m3 * molar_volume (at T_ref, approximation)
            frac_per_s = mol_per_m3_air_per_s * self._params.mol_volume_m3_per_mol
            if kind == "o2_sink":
                rates.append(frac_per_s * self._params.respiratory_quotient)
            elif kind == "co2_source":
                rates.append(frac_per_s)
            else:
                raise ValueError(f"unknown kind: {kind}")
        return rates

    def _solve_profile(
        self,
        profile: SoilProfileView,
        d_eff: list[float],
        source_rate: list[float],
        n: int,
        top_boundary: float,
        source_sign: float,
    ) -> list[float]:
        """Solve steady-state Fick's 2nd law with source and boundaries.

        Discretizes -d/dz (D_eff dC/dz) = source_sign × source_rate
        on cell-centered layers with face-averaged D_eff. Top Dirichlet
        boundary = ``top_boundary``; bottom zero-flux (Neumann).
        """
        if n == 1:
            # Single-layer profile: solve the Dirichlet-top/zero-flux-bottom
            # balance analytically. Flux at top = source_sign · rate · dz.
            # Center concentration = top + 0.5 · source_sign · rate · dz² / D.
            dz0 = profile.layers[0].depth_cm / 100.0
            d0 = max(d_eff[0], _EPS)
            raw = top_boundary + 0.5 * source_sign * source_rate[0] * dz0 * dz0 / d0
            return [max(0.0, min(1.0, raw))]
        # Layer half-thicknesses in meters (centers)
        dz = [profile.layers[i].depth_cm / 100.0 for i in range(n)]
        # Face distances (between cell centers i and i+1)
        face_dz = [0.5 * (dz[i] + dz[i + 1]) for i in range(n - 1)]
        # Harmonic mean of adjacent D_eff at each interior face
        d_face = [
            2.0 * d_eff[i] * d_eff[i + 1] / max(d_eff[i] + d_eff[i + 1], _EPS)
            for i in range(n - 1)
        ]
        a = [0.0] * n
        b = [0.0] * n
        c = [0.0] * n
        rhs = [0.0] * n

        # Row 0: Dirichlet top. Use ghost cell at z=0 with C=top_boundary.
        # Discretization in layer 0:
        #   -(d_face[0] * (C1 - C0) / face_dz[0]) +
        #    (D_top * (C0 - top) / (dz[0] / 2)) = source_sign * rate * dz[0]
        d_top = d_eff[0]
        dz_top = dz[0] / 2.0
        # Coefficients:
        b[0] = d_face[0] / face_dz[0] + d_top / dz_top
        c[0] = -d_face[0] / face_dz[0]
        rhs[0] = source_sign * source_rate[0] * dz[0] + d_top * top_boundary / dz_top

        # Interior rows
        for i in range(1, n - 1):
            aL = d_face[i - 1] / face_dz[i - 1]
            aR = d_face[i] / face_dz[i]
            a[i] = -aL
            b[i] = aL + aR
            c[i] = -aR
            rhs[i] = source_sign * source_rate[i] * dz[i]

        # Row n-1: bottom zero-flux. Only left face.
        aL = d_face[n - 2] / face_dz[n - 2]
        a[n - 1] = -aL
        b[n - 1] = aL
        c[n - 1] = 0.0
        rhs[n - 1] = source_sign * source_rate[n - 1] * dz[n - 1]

        solution = solve_tridiagonal(a, b, c, rhs)
        # Clamp to physically meaningful non-negative fractions.
        return [max(0.0, min(1.0, v)) for v in solution]

    def _microsite_fraction(self, o2_frac: float) -> float:
        """Estimate anaerobic microsite fraction from mean O2.

        Piecewise linear ramp: 1.0 at O2 <= thr/2, linear decrease to
        0.0 at O2 >= 2 × thr. Return value is always clamped to [0, 1]
        to guarantee a physically meaningful fraction even for unusual
        param combinations. Ref: Arah & Smith 1989 heterogeneity model.
        """
        thr = self._params.anaerobic_o2_threshold_frac
        if o2_frac <= 0.0:
            return 1.0
        if o2_frac >= 2.0 * thr:
            return 0.0
        lo = 0.5 * thr
        hi = 2.0 * thr
        if o2_frac <= lo:
            return 1.0
        # Clamp defensively: formula is bounded by the above guards,
        # but the clamp guarantees [0, 1] under any parameter overrides.
        return max(0.0, min(1.0, (hi - o2_frac) / (hi - lo)))
