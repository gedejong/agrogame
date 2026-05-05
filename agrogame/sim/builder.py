from __future__ import annotations

from pathlib import Path

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from dataclasses import dataclass
from agrogame.sim.calendar import Calendar


def build_full_from_preset(profile_name: str) -> FullSimulationOrchestrator:
    """Build a FullSimulationOrchestrator from a soil preset name.

    Centralizes preset loading to avoid duplication across plotting modules.
    """
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    return FullSimulationOrchestrator(profile)


def generate_rain_evap(
    days: int,
    base_rain_mm: float,
    base_evap_mm: float,
    pattern: str = "constant",
) -> tuple[list[float], list[float]]:
    """Generate daily rainfall and evaporation sequences for a small set of patterns.

    - constant: fixed rain and evap
    - seasonal: 30-day sinusoid around base values
    - storms: low background rain + periodic storm spikes
    """
    import math

    if pattern == "seasonal":
        rains = [
            base_rain_mm + 0.8 * base_rain_mm * math.sin(2 * math.pi * (i / 30.0))
            for i in range(days)
        ]
        evaps = [
            base_evap_mm + 0.5 * base_evap_mm * math.sin(2 * math.pi * (i / 30.0))
            for i in range(days)
        ]
    elif pattern == "storms":
        rains = [
            (0.2 * base_rain_mm) + (3.0 * base_rain_mm if (i % 7 == 0) else 0.0)
            for i in range(days)
        ]
        evaps = [base_evap_mm for _ in range(days)]
    else:
        rains = [base_rain_mm for _ in range(days)]
        evaps = [base_evap_mm for _ in range(days)]

    return rains, evaps


def generate_temp_par(
    days: int,
    base_tmin_c: float,
    base_tmax_c: float,
    base_par_mj_m2: float,
    pattern: str = "constant",
) -> tuple[list[float], list[float], list[float]]:
    """Generate daily tmin/tmax/PAR sequences for simple patterns."""
    import math

    if pattern == "seasonal":
        tmins = [
            base_tmin_c + 5.0 * math.sin(2 * math.pi * (i / 30.0)) for i in range(days)
        ]
        tmaxs = [
            base_tmax_c + 7.0 * math.sin(2 * math.pi * (i / 30.0)) for i in range(days)
        ]
        pars = [
            base_par_mj_m2 + 0.5 * base_par_mj_m2 * math.sin(2 * math.pi * (i / 30.0))
            for i in range(days)
        ]
    else:
        tmins = [base_tmin_c for _ in range(days)]
        tmaxs = [base_tmax_c for _ in range(days)]
        pars = [base_par_mj_m2 for _ in range(days)]

    return tmins, tmaxs, pars


@dataclass
class SimulationApp:
    calendar: Calendar


class SimulationBuilder:
    def build(self, profile: SoilProfile) -> SimulationApp:
        orch = FullSimulationOrchestrator(profile)
        return SimulationApp(calendar=orch.calendar)
