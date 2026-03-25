from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

from .constants import DEFAULT_ALBEDO
from .presets import ClimatePreset
from .types import WeatherRecord, WeatherSeries
from .utils import sanitize_weather_series


@dataclass(frozen=True)
class _ScenarioModifiers:
    precip_mult: float = 1.0
    temp_offset_c: float = 0.0
    rh_offset_pct: float = 0.0
    shortwave_mult: float = 1.0


_SCENARIOS: dict[str, _ScenarioModifiers] = {
    "normal": _ScenarioModifiers(),
    "drought": _ScenarioModifiers(
        precip_mult=0.2, temp_offset_c=2.0, rh_offset_pct=-15.0, shortwave_mult=1.1
    ),
    "wet": _ScenarioModifiers(precip_mult=2.0, rh_offset_pct=10.0, shortwave_mult=0.9),
    "hot": _ScenarioModifiers(
        temp_offset_c=5.0, rh_offset_pct=-10.0, shortwave_mult=1.15
    ),
    "cold": _ScenarioModifiers(
        temp_offset_c=-5.0, rh_offset_pct=5.0, shortwave_mult=0.85
    ),
}

_VALID_SCENARIOS = frozenset(_SCENARIOS.keys())


class SyntheticWeatherGenerator:
    def __init__(self, preset: ClimatePreset, seed: int | None = None) -> None:
        self.preset = preset
        self._rng = random.Random(seed)

    def generate(
        self,
        days: int,
        start_date: date,
        scenario: str = "normal",
    ) -> WeatherSeries:
        if scenario not in _VALID_SCENARIOS:
            raise ValueError(
                f"Unknown scenario {scenario!r}; choose from {sorted(_VALID_SCENARIOS)}"
            )
        mods = _SCENARIOS[scenario]
        records = self._generate_base(days, start_date, mods)
        records = self._inject_extremes(records)
        return sanitize_weather_series(WeatherSeries(records))

    def _generate_base(
        self,
        days: int,
        start_date: date,
        mods: _ScenarioModifiers,
    ) -> list[WeatherRecord]:
        p = self.preset
        records: list[WeatherRecord] = []
        for i in range(days):
            d = start_date + timedelta(days=i)
            doy = d.timetuple().tm_yday
            seasonal = math.sin(2.0 * math.pi / 365.0 * (doy - 80))
            tmin = (
                p.annual_mean_tmin_c
                + p.annual_temp_amplitude_c * seasonal
                + mods.temp_offset_c
                + self._rng.gauss(0.0, 1.5)
            )
            tmax = (
                p.annual_mean_tmax_c
                + p.annual_temp_amplitude_c * seasonal
                + mods.temp_offset_c
                + self._rng.gauss(0.0, 1.5)
            )
            if tmax <= tmin:
                tmax = tmin + 1.0
            rh = p.annual_mean_rh_pct + mods.rh_offset_pct + self._rng.gauss(0.0, 5.0)
            wind = max(0.1, p.annual_mean_wind_m_s + self._rng.gauss(0.0, 0.8))
            sw = max(
                0.0,
                p.annual_mean_shortwave_mj_m2
                * mods.shortwave_mult
                * (1.0 + 0.3 * seasonal)
                + self._rng.gauss(0.0, 1.5),
            )
            precip = self._generate_daily_precip(p, mods, d.month)
            records.append(
                WeatherRecord(
                    day=d,
                    tmin_c=tmin,
                    tmax_c=tmax,
                    relative_humidity_pct=rh,
                    wind_m_s=wind,
                    shortwave_mj_m2=sw,
                    net_radiation_mj_m2=None,
                    albedo=DEFAULT_ALBEDO,
                    precip_mm=precip,
                )
            )
        return records

    def _generate_daily_precip(
        self, p: ClimatePreset, mods: _ScenarioModifiers, month: int
    ) -> float:
        """Exponential distribution for daily rainfall with monthly seasonality."""
        mean = p.annual_mean_precip_mm_day * mods.precip_mult
        # Apply monthly weight if defined (12 values, mean-normalized)
        if p.rainfall_monthly_weights and len(p.rainfall_monthly_weights) == 12:
            weight = p.rainfall_monthly_weights[month - 1]
            mean *= weight
        if mean <= 0.01:
            return 0.0
        return max(0.0, self._rng.expovariate(1.0 / mean))

    def _inject_extremes(self, records: list[WeatherRecord]) -> list[WeatherRecord]:
        p = self.preset
        result = list(records)
        i = 0
        while i < len(result):
            if (
                p.heatwave_probability > 0
                and self._rng.random() < p.heatwave_probability
            ):
                duration = self._rng.randint(3, 7)
                result = self._apply_heatwave(
                    result, i, duration, p.heatwave_intensity_c
                )
                i += duration
                continue
            if p.frost_probability > 0 and self._rng.random() < p.frost_probability:
                duration = self._rng.randint(1, 3)
                result = self._apply_frost(result, i, duration, p.frost_intensity_c)
                i += duration
                continue
            if (
                p.heavy_rain_probability > 0
                and self._rng.random() < p.heavy_rain_probability
            ):
                result = self._apply_heavy_rain(result, i, p.heavy_rain_intensity_mm)
            i += 1
        return result

    @staticmethod
    def _apply_heatwave(
        records: list[WeatherRecord],
        start: int,
        duration: int,
        intensity_c: float,
    ) -> list[WeatherRecord]:
        for j in range(start, min(start + duration, len(records))):
            r = records[j]
            records[j] = WeatherRecord(
                day=r.day,
                tmin_c=r.tmin_c + intensity_c,
                tmax_c=r.tmax_c + intensity_c,
                relative_humidity_pct=(r.relative_humidity_pct or 50.0) - 15.0,
                wind_m_s=r.wind_m_s,
                shortwave_mj_m2=(r.shortwave_mj_m2 or 15.0) * 1.2,
                net_radiation_mj_m2=None,
                albedo=r.albedo,
                precip_mm=0.0,
            )
        return records

    @staticmethod
    def _apply_frost(
        records: list[WeatherRecord],
        start: int,
        duration: int,
        intensity_c: float,
    ) -> list[WeatherRecord]:
        for j in range(start, min(start + duration, len(records))):
            r = records[j]
            frost_tmin = r.tmin_c + intensity_c
            records[j] = WeatherRecord(
                day=r.day,
                tmin_c=frost_tmin,
                tmax_c=max(frost_tmin + 3.0, r.tmax_c + intensity_c * 0.5),
                relative_humidity_pct=r.relative_humidity_pct,
                wind_m_s=r.wind_m_s,
                shortwave_mj_m2=r.shortwave_mj_m2,
                net_radiation_mj_m2=None,
                albedo=r.albedo,
                precip_mm=r.precip_mm,
            )
        return records

    @staticmethod
    def _apply_heavy_rain(
        records: list[WeatherRecord],
        idx: int,
        intensity_mm: float,
    ) -> list[WeatherRecord]:
        if idx >= len(records):
            return records
        r = records[idx]
        records[idx] = WeatherRecord(
            day=r.day,
            tmin_c=r.tmin_c,
            tmax_c=r.tmax_c,
            relative_humidity_pct=95.0,
            wind_m_s=r.wind_m_s,
            shortwave_mj_m2=(r.shortwave_mj_m2 or 10.0) * 0.4,
            net_radiation_mj_m2=None,
            albedo=r.albedo,
            precip_mm=intensity_mm,
        )
        return records
