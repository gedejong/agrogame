from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "day": self.day.isoformat(),
            "tmin_c": self.tmin_c,
            "tmax_c": self.tmax_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "wind_m_s": self.wind_m_s,
            "shortwave_mj_m2": self.shortwave_mj_m2,
            "net_radiation_mj_m2": self.net_radiation_mj_m2,
            "albedo": self.albedo,
            "precip_mm": self.precip_mm,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WeatherRecord:
        return cls(
            day=date.fromisoformat(str(data["day"])),
            tmin_c=float(data["tmin_c"]),
            tmax_c=float(data["tmax_c"]),
            relative_humidity_pct=data.get("relative_humidity_pct"),
            wind_m_s=data.get("wind_m_s"),
            shortwave_mj_m2=data.get("shortwave_mj_m2"),
            net_radiation_mj_m2=data.get("net_radiation_mj_m2"),
            albedo=data.get("albedo"),
            precip_mm=data.get("precip_mm"),
        )


@dataclass
class WeatherSeries:
    records: List[WeatherRecord]
