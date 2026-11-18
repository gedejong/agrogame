---
module: agrogame.weather
doc_type: module
references:
  - "FAO-56 (Allen et al. 1998) — reference ET drivers (tmin, tmax, rh, wind, rs)"
  - "Richardson 1981 — stochastic weather generation"
  - "WMO World Weather Information Service — DMN Niamey station normals, 1961-1990"
  - "NASA POWER Climatology API v2.10.1 — ALLSKY_SFC_SW_DWN, 2001-2020"
key_classes: [WeatherRecord, WeatherSeries, ClimatePreset, ClimateLibrary, SyntheticWeatherGenerator]
key_events: []
primary_tests:
  - tests/test_weather_generator.py
  - tests/test_weather_ingestion.py
  - tests/test_weather_interpolation.py
related_adrs: [ADR-002, ADR-006, ADR-019]
---

# Weather System

## Data Sources

### File Loading
Load historical weather from CSV or JSON via `load_weather(path)`. Required
columns: `date`, `tmin_c`, `tmax_c`. Optional: `rh_pct`, `wind_m_s`,
`rs_mj_m2`, `rn_mj_m2`, `albedo`, `precip_mm`. Results are cached for
repeated access.

### NASA POWER
`load_weather_auto(lat, lon, start, end)` fetches daily data from the
NASA POWER API (no API key required). Parameters: T2M_MAX, T2M_MIN,
RH2M, WS10M, ALLSKY_SFC_SW_DWN, PRECTOTCORR.

### Synthetic Generation
`SyntheticWeatherGenerator(preset, seed)` produces `WeatherSeries` from
a `ClimatePreset`. Scenarios: `normal`, `drought`, `wet`, `hot`, `cold`.

### OpenWeather (planned)
Integration with the OpenWeather API is planned for a follow-up PR.

## Climate Presets

YAML presets in `data/climate/presets.yaml` define regional baselines:

| Preset | Location | Mean Tmax | Precip | Seasonal shape |
|--------|----------|-----------|--------|----------------|
| `netherlands_temperate` | 52°N, 5.5°E | 14°C | 2.3 mm/d | legacy sinusoid (moves in #587) |
| `kenya_highlands` | 0.4°S, 36.9°E | 24°C | 3.5 mm/d | legacy sinusoid (moves in #588) |
| `sahel_arid` | 14°N, 2°E | 36.19°C | 1.2 mm/d | station monthly normals |

Load with `load_climate_presets()`.

### Monthly normals (ADR-019)

A preset may carry 12-element arrays `monthly_mean_tmin_c`,
`monthly_mean_tmax_c` and `monthly_mean_shortwave_mj_m2` (Jan→Dec). The
generator then takes each day's base Tmin, Tmax and shortwave from its calendar
month's entry and adds the usual scenario offsets and daily noise. The lookup
keys on the month alone, so multi-year series have no seam at New Year or
29 February. Without the arrays the legacy formula applies: one sinusoid
`sin(2π/365·(doy − 80))`, peaking about 20 June for every preset, with
shortwave fixed at ±30%. That shape inverted the Kenya highland seasons and put
the Sahel's heat in its monsoon (#560).

Shipped presets move onto cited station normals, one per PR (ADR-019):

- `sahel_arid`: Tmin/Tmax from the Direction de la Météorologie Nationale du
  Niger via WMO WWIS, Niamey, 1961-1990; shortwave from NASA POWER v2.10.1
  (`ALLSKY_SFC_SW_DWN`, 2001-2020) at the station point.
- `netherlands_temperate` (#587): KNMI De Bilt daily TN, TX and Q, 1991-2020.
- `kenya_highlands` (#588): KMD via WMO WWIS, Nyeri, 1980-2018; NASA POWER
  shortwave.

The loader checks that Tmin and Tmax arrays come together, that Tmin < Tmax in
every month, and that each array's mean equals its `annual_mean_*` field within
0.05. `annual_temp_amplitude_c` is informational once the arrays are present.
The extremes injector still runs on top of the normals and biases them warm
(#579); the fidelity test in `tests/test_weather_generator.py` disables it.

## Derived Variables

### Photoperiod
Daylength from latitude and day-of-year (Spencer 1971):

$$\delta = 0.4093 \sin\!\left(\frac{2\pi}{365} \cdot \text{DOY} - 1.405\right)$$

$$\omega_s = \arccos\!\left(-\tan\phi \cdot \tan\delta\right)$$

$$N = \frac{24}{\pi} \omega_s$$

Clamped to [0, 24] h for polar regions. Used by `PhenologyRuntime` to
replace the previously hardcoded 12 h value.

### VPD
Vapor pressure deficit via Tetens/FAO-56 saturation curve.

### Net Radiation
Derived from shortwave when missing: $R_n = R_s (1 - \alpha)$.

## Interpolation

`interpolate_weather_series(series)` fills gaps:
- Continuous fields: linear interpolation between neighbors
- Precipitation: filled with 0.0
- Albedo: filled with 0.23 (FAO-56 default)

## Extreme Weather Events

The synthetic generator injects probabilistic extremes:
- **Heatwave**: 3-7 day burst, temperature + intensity, no rain
- **Frost**: 1-3 days, tmin set to frost intensity
- **Heavy rain**: single day, precipitation set to intensity, RH 95%

Probabilities and intensities are configured per climate preset.

## Caching

- `load_weather`: `lru_cache(16)` on file path
- `load_climate_presets`: `lru_cache(4)` on file path
- `saturation_vapor_pressure_kpa`: `lru_cache(512)`
- `photoperiod_h`: `lru_cache(512)`
