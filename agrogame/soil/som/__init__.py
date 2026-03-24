"""Soil Organic Matter (SOM) module — placeholder.

Current status: SimpleSOMRuntime emits substrate availability per layer
based on PAR and smoothed root fractions. This is a stop-gap provider
until AGRO-71 implements real SOM pools (active/slow/passive C and N).

Roadmap (AGRO-71):
- Multi-pool C/N decomposition (RothC or Century-like)
- Temperature and moisture response functions
- Humification and CO2 respiration fluxes
- Integration with microbes module for enzyme-mediated turnover
"""

from agrogame.soil.som.runtime import SimpleSOMRuntime

__all__ = ["SimpleSOMRuntime"]
