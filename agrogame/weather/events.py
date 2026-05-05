from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agrogame.events.base import BaseEvent


@dataclass(frozen=True)
class DailyWeather(BaseEvent):
    day: date = field(default_factory=date.today)
    tmin_c: float = 0.0
    tmax_c: float = 0.0
    relative_humidity_pct: float | None = None
    wind_m_s: float | None = None
    net_radiation_mj_m2: float | None = None
    shortwave_mj_m2: float | None = None
    precip_mm: float | None = None
