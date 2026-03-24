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

| Preset | Location | Mean Tmax | Precip |
|--------|----------|-----------|--------|
| `netherlands_temperate` | 52°N, 5.5°E | 14°C | 2.3 mm/d |
| `kenya_highlands` | 0.4°S, 36.9°E | 24°C | 3.5 mm/d |
| `sahel_arid` | 14°N, 2°E | 36°C | 1.2 mm/d |

Load with `load_climate_presets()`.

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
