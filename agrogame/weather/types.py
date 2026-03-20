from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional


@dataclass(frozen=True)
class WeatherRecord:
    day: date
    tmin_c: float
    tmax_c: float
    relative_humidity_pct: Optional[float] = None
    wind_m_s: Optional[float] = None
    shortwave_mj_m2: Optional[float] = None  # Rs
    net_radiation_mj_m2: Optional[float] = None  # Rn
    albedo: Optional[float] = None
    precip_mm: Optional[float] = None


@dataclass
class WeatherSeries:
    records: List[WeatherRecord]
