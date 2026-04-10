"""Redox dynamics module — daily Eh update and greenhouse gas processes."""

from __future__ import annotations

import math
from typing import Optional

from agrogame.events import EventBus
from agrogame.soil.redox.state import RedoxState, DominantAcceptor
from agrogame.soil.redox.params import RedoxParams
from agrogame.soil.redox.events import (
    RedoxChanged,
    CH4Emitted,
    CH4Oxidized,
)


class RedoxModule:
    """Computes daily Eh per layer and produces CH4.

    Eh is driven by water-filled pore space (WFPS) as a proxy for oxygen
    availability. The module uses a sigmoid Eh-WFPS curve with first-order
    exponential decay toward the equilibrium value (tau ~2 days).

    Ref: Reddy & DeLaune 2008, Biogeochemistry of Wetlands;
         Stumm & Morgan 1996, Aquatic Chemistry.
    """

    def __init__(
        self,
        params: RedoxParams,
        state: RedoxState,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self.params = params
        self.state = state
        self.event_bus = event_bus

    # --- Public API ---

    def daily_step(
        self,
        theta: list[float],
        saturation: list[float],
        root_fractions: list[float],
        temperature_c: float,
    ) -> None:
        """Advance redox state by one day.

        Args:
            theta: Volumetric water content per layer.
            saturation: Saturation water content per layer.
            root_fractions: Root density fraction per layer (0-1).
            temperature_c: Mean daily temperature (°C).
        """
        n = min(len(theta), len(self.state.eh_mv))
        for i in range(n):
            wfps = theta[i] / max(saturation[i], 1e-6)
            # Rhizosphere effect: roots create oxidized zones
            # Ref: Colmer 2003, Plant Cell Environ — radial O2 loss from roots
            rf = root_fractions[i] if i < len(root_fractions) else 0.0
            effective_wfps = max(
                0.0, wfps - rf * self.params.rhizosphere_wfps_reduction
            )
            # Compute equilibrium Eh and decay toward it
            eq_eh = self._equilibrium_eh(effective_wfps)
            self.state.eh_mv[i] = self._decay_toward(
                self.state.eh_mv[i], eq_eh, self.params.tau_days
            )
            # Update dominant acceptor
            self.state.dominant_acceptor[i] = self._classify_acceptor(
                self.state.eh_mv[i]
            )
            # Emit redox changed event
            if self.event_bus:
                self.event_bus.emit(
                    RedoxChanged(
                        layer=i,
                        eh_mv=self.state.eh_mv[i],
                        dominant_acceptor=self.state.dominant_acceptor[i].value,
                    )
                )
        # CH4 production and oxidation
        self._process_methane(n, temperature_c)

    # --- N2O/N2 partitioning (called by NitrogenCycle) ---

    @staticmethod
    def n2o_fraction(eh_mv: float) -> float:
        """Fraction of denitrified N emitted as N2O (vs N2).

        At intermediate Eh (~150 mV), N2O reductase is inhibited and
        most denitrified N escapes as N2O. At very low Eh, complete
        reduction to N2 dominates.

        Ref: Firestone & Davidson 1989, Exchange of Trace Gases;
             Weier et al. 1993, FEMS Microbiol Ecol.
        """
        # Sigmoid: peaks ~0.7 at Eh=150, drops to ~0.05 at Eh<-100
        x = (eh_mv - 50.0) / 80.0
        return 0.05 + 0.65 / (1.0 + math.exp(-x))

    # --- Internal ---

    def _equilibrium_eh(self, wfps: float) -> float:
        """Sigmoid mapping from WFPS to equilibrium Eh.

        Ref: Simplified from Reddy & DeLaune 2008, Table 2.1.
        """
        p = self.params
        x = p.sigmoid_k * (wfps - p.sigmoid_midpoint)
        sigmoid = 1.0 / (1.0 + math.exp(-x))
        return p.eh_max_mv - (p.eh_max_mv - p.eh_min_mv) * sigmoid

    @staticmethod
    def _decay_toward(current: float, target: float, tau: float) -> float:
        """First-order exponential decay: current → target with time constant tau."""
        if tau <= 0.0:
            return target
        alpha = 1.0 - math.exp(-1.0 / tau)
        return current + alpha * (target - current)

    @staticmethod
    def _classify_acceptor(eh_mv: float) -> DominantAcceptor:
        """Classify dominant electron acceptor from Eh.

        Ref: Stumm & Morgan 1996, Aquatic Chemistry, redox ladder.
        """
        if eh_mv > 300.0:
            return DominantAcceptor.OXYGEN
        if eh_mv > 100.0:
            return DominantAcceptor.NITRATE
        if eh_mv > -100.0:
            return DominantAcceptor.IRON
        return DominantAcceptor.METHANOGENESIS

    def _process_methane(self, n_layers: int, temperature_c: float) -> None:
        """Produce CH4 in reducing layers, oxidize in aerobic surface.

        CH4 production: only when Eh < -200 mV, Q10 temperature scaling.
        CH4 oxidation: aerobic surface layer oxidizes a fraction.

        Ref: Le Mer & Roger 2001, Eur J Soil Biol — CH4 cycling;
             IPCC 2006 Guidelines, Vol 4, Ch 5 — wetland emissions.
        """
        p = self.params
        total_ch4 = 0.0
        for i in range(n_layers):
            eh = self.state.eh_mv[i]
            if eh >= -200.0:
                continue
            # Q10 temperature scaling
            # Ref: Conrad 2002, FEMS Microbiol Ecol — methanogenesis Q10
            q10_factor = p.ch4_q10 ** ((temperature_c - p.ch4_ref_temp_c) / 10.0)
            # Severity: more negative Eh → more CH4
            severity = min(1.0, (-200.0 - eh) / 100.0)
            produced = p.ch4_base_rate_kg_c_ha_day * q10_factor * severity
            total_ch4 += produced
            if self.event_bus and produced > 0.0:
                self.event_bus.emit(CH4Emitted(layer=i, amount_kg_c_ha=produced))

        # Surface oxidation: aerobic surface layer oxidizes upward-moving CH4
        if total_ch4 > 0.0 and n_layers > 0:
            surface_eh = self.state.eh_mv[0]
            if surface_eh > 0.0:
                oxidized = total_ch4 * p.ch4_oxidation_fraction
                if self.event_bus and oxidized > 0.0:
                    self.event_bus.emit(CH4Oxidized(layer=0, amount_kg_c_ha=oxidized))
