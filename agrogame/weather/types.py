from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class WeatherRecord:
    day: date
    tmin_c: float
    tmax_c: float
    relative_humidity_pct: float | None = None
    wind_m_s: float | None = None
    shortwave_mj_m2: float | None = None  # Rs
    net_radiation_mj_m2: float | None = None  # Rn
    albedo: float | None = None
    precip_mm: float | None = None

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
    records: list[WeatherRecord]
