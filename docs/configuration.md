# Configuration

AgroGame provides versioned JSON Schemas and a small CLI to validate and compose
configuration files. This page is the human-readable reference for every
configuration type: one parameter table per schema, with units, ranges, defaults,
and cross-links to the model docs that consume each parameter.

!!! note "Schemas are the source of truth"
    The JSON Schemas under
    [`agrogame/config/schemas/`](https://github.com/gedejong/agrogame/tree/main/agrogame/config/schemas)
    define units (via field names) and ranges (`minimum` / `maximum` / `enum`).
    The tables below are a **mirror** maintained by hand. If a table and its
    schema ever disagree, the schema wins — please open an issue (or a PR fixing
    the table). Where a field is unbounded in the schema, the table gives an
    **agronomically sensible recommended range, explicitly marked `guidance`**;
    those bounds are advisory, not enforced by validation.

## Schemas and tools

- Schemas live under `agrogame/config/schemas/` and cover: crop parameters, crop
  presets, soil, weather series (JSON), climate presets, management events, and
  the economy price table.
- Validate a file against a schema:
  ```bash
  poetry run agrogame validate crop data/samples/crops.yaml
  poetry run agrogame validate soil data/soils/presets.yaml
  ```
- Compose multiple layers into a final YAML (later files override earlier):
  ```bash
  poetry run agrogame build crop out.yaml base.yaml override.yaml
  ```
- Watch files and emit a `ConfigReloaded` event on changes (for UIs/integration):
  ```bash
  poetry run agrogame watch crop data/samples/crops.yaml
  ```

Defaults listed below are the values applied by the preset loaders
(`agrogame/plant/presets.py`, `agrogame/weather/presets.py`) when an optional
field is omitted; required fields have no default and must be supplied.

---

## Crop parameters — `crop.json`

The minimal thermal-time / roots / biomass parameter set used by the core
growth engine (distinct from the richer [crop preset](#crop-preset-crop_presetjson)).
A file is `{ "crops": { "<key>": { …cropParameters… } } }`.

- **Schema:** [`crop.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/crop.json)
  (with [`common.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/common.json))
- **Model docs:** [Phenology](phenology.md) · [Canopy](canopy.md) · [Plant](plant.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `name` | string | — | — | *(required)* | Crop identifier or human-readable name. |
| `thermal_time.base_temp_c` | number | °C | 0–15 | *(required)* | Base temperature below which no thermal time accrues. |
| `thermal_time.emergence_dd` | number | °C·day (GDD) | > 0 | *(required)* | Growing-degree-days from sowing to emergence. |
| `thermal_time.flowering_dd` | number | °C·day (GDD) | > 0 | *(required)* | GDD from sowing to flowering. |
| `thermal_time.maturity_dd` | number | °C·day (GDD) | > 0 | *(required)* | GDD from sowing to physiological maturity. |
| `roots.max_depth_cm` | number | cm | > 0 (guidance: 30–300) | *(required)* | Maximum rooting depth. |
| `roots.growth_rate_cm_per_day` | number | cm/day | > 0 (guidance: 0.5–4) | *(required)* | Downward root-front extension rate. |
| `roots.distribution` | array[number] | fraction per layer | ≥ 3 items, each ≥ 0 | *(required)* | Relative root density by layer (top→bottom). |
| `biomass.rue_g_per_mj` | number | g DM / MJ | > 0 (guidance: 1–4) | *(required)* | Radiation-use efficiency (biomass per MJ intercepted PAR). |
| `biomass.harvest_index` | number | fraction | 0 < HI ≤ 1 | *(required)* | Fraction of above-ground biomass in harvested organ. |
| `biomass.partition_vegetative` | object[string→number] | fraction | each ≥ 0 | *(required)* | Vegetative-stage dry-matter partitioning by organ. |
| `biomass.partition_reproductive` | object[string→number] | fraction | each ≥ 0 | *(required)* | Reproductive-stage dry-matter partitioning by organ. |

`thermal_time` allows additional properties, so crop-specific extras can be
attached without a schema change.

---

## Crop preset — `crop_preset.json`

The richer preset consumed by `CropLibrary.get_preset(crop_key, climate_key)`:
phenology, canopy dynamics, roots, and optional per-climate overrides. A file is
`{ "crops": { "<key>": { …cropPreset… } } }`.

- **Schema:** [`crop_preset.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/crop_preset.json)
- **Model docs:** [Phenology](phenology.md) · [Canopy](canopy.md) · [Plant](plant.md)

### Preset top level

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `name` | string | — | — | *(required)* | Human-readable crop name. |
| `phenology` | object | — | see below | *(required)* | Thermal-time development parameters. |
| `canopy` | object | — | see below | *(required)* | Light interception, RUE, LAI and stress dynamics. |
| `roots` | object | — | see below | *(optional)* | Root growth parameters. |
| `n_fixation_credit_kg_ha` | number | kg N/ha | ≥ 0 | 0.0 | Symbiotic N credited to the soil (legumes). |
| `climate_overrides` | object | — | — | *(none)* | Per-climate parameter overrides (e.g. calibrated posteriors). |

### `phenology`

- **Model doc:** [Phenology](phenology.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `base_temperature_c` | number | °C | guidance: 0–15 | *(required)* | Base temperature for GDD accrual. |
| `max_temperature_c` | number | °C | guidance: 25–45 | *(required)* | Upper cutoff temperature for GDD accrual. |
| `emergence_gdd` | number | °C·day (GDD) | ≥ 0 | *(required)* | GDD from sowing to emergence. |
| `flowering_gdd` | number | °C·day (GDD) | ≥ 0 | *(required)* | GDD from sowing to flowering. |
| `maturity_gdd` | number | °C·day (GDD) | ≥ 0 | *(required)* | GDD from sowing to maturity. |
| `photoperiod_sensitivity` | number \| null | 0–1 multiplier | guidance: 0–1 | null (disabled) | Day-length sensitivity of development. |
| `vernalization_required_units` | number \| null | vernalization days | guidance: 0–70 | null (disabled) | Cold requirement before flowering (winter crops). |

### `canopy`

- **Model doc:** [Canopy](canopy.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `extinction_coefficient_k` | number | unitless (Beer–Lambert) | 0–1 | *(required)* | Canopy light-extinction coefficient. |
| `rue_g_per_mj` | number | g DM / MJ | ≥ 0 (guidance: 1–4) | *(required)* | Radiation-use efficiency. |
| `sla_m2_per_g` | number | m²/g | ≥ 0 (guidance: 0.01–0.04) | *(required)* | Specific leaf area (leaf area per g leaf DM). |
| `lai_max` | number | m²/m² | ≥ 0 (guidance: 1–8) | *(required)* | Maximum leaf area index. |
| `senescence_rate_per_day` | number | /day | ≥ 0 | 0.01 | Baseline LAI senescence rate. |
| `temp_base_c` | number | °C | guidance: 0–15 | 8.0 | Cardinal base temp for RUE scaling. |
| `temp_opt_c` | number | °C | guidance: 20–35 | 30.0 | Cardinal optimum temp (RUE factor = 1). |
| `temp_max_c` | number | °C | guidance: 35–48 | 42.0 | Cardinal max temp (RUE factor = 0). |
| `initial_lai_at_emergence` | number | m²/m² | ≥ 0 | 0.1 | LAI bootstrap value at emergence. |
| `senescence_vegetative_fraction` | number | fraction | 0–1 | 0.1 | Senescence-rate multiplier during vegetative stage. |
| `leaf_fraction_vegetative` | number | fraction | 0–1 | 0.7 | Daily biomass allocated to leaf, vegetative stage. |
| `leaf_fraction_flowering` | number | fraction | 0–1 | 0.4 | Daily biomass allocated to leaf, flowering stage. |
| `leaf_fraction_grain_fill` | number | fraction | 0–1 | 0.15 | Daily biomass allocated to leaf, grain-fill stage. |
| `senescence_flowering_fraction` | number | multiplier | ≥ 0 | 0.5 | Senescence multiplier at flowering. |
| `senescence_grain_fill_max` | number | multiplier | ≥ 0 | 2.0 | Peak senescence multiplier at end of grain fill. |
| `grain_fill_duration_gdd` | number | °C·day (GDD) | ≥ 0 | 900.0 | GDD span over which senescence ramps. |
| `stress_memory_days` | integer | days | ≥ 1 | 7 | Window for running-average water stress. |
| `wilt_stress_threshold` | number | fraction | 0–1 | 0.3 | Water-stress level below which wilting damage begins. |
| `wilt_days_for_damage` | integer | days | ≥ 1 | 5 | Consecutive stressed days before LAI loss. |
| `wilt_lai_loss_fraction` | number | fraction | 0–1 | 0.1 | LAI lost per wilting-damage event. |
| `harvest_index` | number | fraction | 0–1 | 0.45 | Fixed HI (legacy path; used when `grains_per_g_source` = 0). |
| `grains_per_g_source` | number | grains·m⁻² per g·m⁻² | ≥ 0 | 0.0 | Grain number per unit peri-anthesis assimilate (0 = fixed-HI). |
| `grain_set_window_gdd` | number | °C·day (GDD) | ≥ 0 | 200.0 | Peri-anthesis critical window for grain set. |
| `potential_kernel_weight_mg` | number | mg | ≥ 0 (guidance: 20–300) | 40.0 | Potential single-kernel weight (CERES G2). |
| `kernel_fill_rate_mg_per_grain_day` | number | mg/grain/day | ≥ 0 | 1.0 | Potential single-kernel daily fill rate. |
| `hi_max` | number | fraction | 0–1 | 0.55 | Emergent-HI cap (cereal ceiling). |
| `remobilization_fraction` | number | fraction/day | 0–1 | 0.0 | Daily stem biomass remobilised to grain. |
| `leaf_remob_fraction` | number | fraction/day | 0–1 | 0.0 | Daily leaf pool remobilised to grain. |
| `frost_threshold_c` | number | °C | guidance: −5–2 | 0.0 | Tmin below which frost damages LAI. |
| `frost_damage_fraction` | number | fraction | 0–1 | 0.3 | LAI lost per frost event. |
| `heat_damage_threshold_c` | number | °C | guidance: 30–40 | 35.0 | Tmax above which flowering heat reduces grain. |
| `heat_grain_reduction_fraction` | number | fraction | 0–1 | 0.5 | Grain reduction per heat event at flowering. |
| `waterlog_days_for_damage` | integer | days | ≥ 1 | 3 | Consecutive saturated days before LAI loss. |
| `waterlog_lai_loss_fraction` | number | fraction | 0–1 | 0.15 | LAI lost per waterlogging-damage event. |

### `roots`

- **Model doc:** [Plant](plant.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `max_depth_cm` | number | cm | ≥ 0 (guidance: 30–300) | 120.0 | Maximum rooting depth. |
| `growth_rate_cm_per_day` | number | cm/day | ≥ 0 (guidance: 0.5–4) | 1.5 | Downward root-front extension rate. |
| `distribution` | string | — | `exponential`, `uniform`, `taproot` | `exponential` | Root density profile shape. |

---

## Soil — `soil.json`

Layered soil profiles used by the water balance and biogeochemistry modules. A
file is `{ "soils": { "<key>": { "name": …, "layers": [ …soilLayer… ] } } }`;
each profile needs **at least 3 layers**.

- **Schema:** [`soil.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/soil.json)
  (texture enum from [`common.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/common.json))
- **Model docs:** [Water balance](water.md) · [Nitrogen](nitrogen.md) · [Soil](soil.md)

### Profile

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `name` | string | — | — | *(required)* | Human-readable profile name. |
| `layers` | array[object] | — | ≥ 3 items | *(required)* | Ordered soil layers (top→bottom). |

### Layer (`layers[]`) — all fields required

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `depth_cm` | number | cm | > 0 (guidance: 5–100) | *(required)* | Layer thickness. |
| `texture` | string | — | `sand`, `sandy_loam`, `loam`, `clay_loam`, `clay`, `peat` | *(required)* | USDA-style texture class. |
| `field_capacity` | number | m³/m³ (vol. water) | 0–0.8 | *(required)* | Water content at field capacity (θ_fc). |
| `wilting_point` | number | m³/m³ (vol. water) | 0–0.8 | *(required)* | Water content at permanent wilting point (θ_wp). |
| `saturation` | number | m³/m³ (vol. water) | 0–0.8 | *(required)* | Saturated water content (θ_sat, ≈ porosity). |
| `bulk_density_g_cm3` | number | g/cm³ | > 0 (guidance: 1.0–1.8) | *(required)* | Dry bulk density. |
| `ksat_mm_per_hour` | number | mm/hr | > 0 (guidance: 1–200) | *(required)* | Saturated hydraulic conductivity. |
| `organic_matter_pct` | number | % (mass) | ≥ 0 (guidance: 0–15) | *(required)* | Soil organic matter content. |
| `initial_no3_kg_ha` | number | kg N/ha | guidance: 0–100 | *(required)* | Initial nitrate-N in the layer. |
| `initial_nh4_kg_ha` | number | kg N/ha | guidance: 0–50 | *(required)* | Initial ammonium-N in the layer. |
| `initial_p_kg_ha` | number | kg P/ha | guidance: 0–100 | *(required)* | Initial plant-available phosphorus in the layer. |

Physical consistency (not enforced by the schema): expect
`wilting_point < field_capacity < saturation`.

---

## Weather series — `weather.json`

A daily driver time series: a JSON **array** of per-day records. `date`,
`tmin_c`, `tmax_c` are required; the remaining fields may be `null` (or omitted),
in which case the ET / weather engine estimates them.

- **Schema:** [`weather.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/weather.json)
- **Model docs:** [Weather](weather.md) · [ET (PT/PM + VPD)](et.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `date` | string | ISO date | `YYYY-MM-DD` | *(required)* | Calendar date of the record. |
| `tmin_c` | number | °C | guidance: −40–40 | *(required)* | Daily minimum air temperature. |
| `tmax_c` | number | °C | guidance: −30–55 | *(required)* | Daily maximum air temperature. |
| `rh_pct` | number \| null | % | guidance: 0–100 | null (estimated) | Mean relative humidity. |
| `wind_m_s` | number \| null | m/s | guidance: 0–20 | null (estimated) | Mean wind speed (typically at 2 m). |
| `rs_mj_m2` | number \| null | MJ/m²/day | guidance: 0–35 | null (estimated) | Incoming shortwave (solar) radiation. |
| `rn_mj_m2` | number \| null | MJ/m²/day | guidance: −5–30 | null (estimated) | Net radiation. |
| `albedo` | number \| null | fraction | guidance: 0–1 | null (estimated) | Surface albedo. |
| `precip_mm` | number \| null | mm | guidance: 0–200 | null (0) | Daily precipitation. |

---

## Climate preset — `climate.json`

Statistical climate descriptors used by the stochastic weather generator to
synthesise a `weather.json` series. A file is
`{ "climates": { "<key>": { …climatePreset… } } }`.

- **Schema:** [`climate.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/climate.json)
- **Model docs:** [Weather](weather.md) · [ET (PT/PM + VPD)](et.md)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `name` | string | — | — | *(required)* | Human-readable climate name. |
| `latitude_deg` | number | ° | −90–90 | *(required)* | Latitude (drives day length / extraterrestrial radiation). |
| `longitude_deg` | number | ° | −180–180 | *(required)* | Longitude. |
| `annual_mean_tmin_c` | number | °C | guidance: −20–30 | *(required)* | Annual mean daily minimum temperature. |
| `annual_mean_tmax_c` | number | °C | guidance: −10–45 | *(required)* | Annual mean daily maximum temperature. |
| `annual_temp_amplitude_c` | number | °C | ≥ 0 (guidance: 0–25) | *(required)* | Seasonal (summer–winter) temperature amplitude. |
| `annual_mean_precip_mm_day` | number | mm/day | ≥ 0 (guidance: 0–15) | *(required)* | Annual mean daily precipitation. |
| `annual_mean_rh_pct` | number | % | 0–100 | *(required)* | Annual mean relative humidity. |
| `annual_mean_wind_m_s` | number | m/s | ≥ 0 (guidance: 0–10) | *(required)* | Annual mean wind speed. |
| `annual_mean_shortwave_mj_m2` | number | MJ/m²/day | ≥ 0 (guidance: 5–30) | *(required)* | Annual mean shortwave radiation. |
| `rainfall_monthly_weights` | array[number] | relative weight | exactly 12 items, each ≥ 0 | *(none → uniform)* | Monthly rainfall distribution weights (Jan→Dec). |
| `heatwave_probability` | number | probability | 0–1 | 0.0 | Daily probability of a heatwave onset. |
| `frost_probability` | number | probability | 0–1 | 0.0 | Daily probability of a frost event. |
| `heavy_rain_probability` | number | probability | 0–1 | 0.0 | Daily probability of a heavy-rain event. |
| `heatwave_intensity_c` | number | °C | ≥ 0 | 8.0 | Temperature anomaly added during a heatwave. |
| `frost_intensity_c` | number | °C | guidance: −15–0 | −5.0 | Temperature applied during a frost event. |
| `heavy_rain_intensity_mm` | number | mm | ≥ 0 | 40.0 | Rainfall added during a heavy-rain event. |

---

## Management events — `management.json`

Scheduled agronomic operations for a season. All three sections are optional;
`additionalProperties` is `false`, so only the keys below are allowed.

- **Schema:** [`management.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/management.json)
- **Model docs:** [Plant](plant.md) · [Nitrogen](nitrogen.md) · [Phosphorus](phosphorus.md) · [Water balance](water.md)

### `planting` (object)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `date` | string | ISO date | `YYYY-MM-DD` | *(required)* | Sowing date. |
| `crop` | string | — | — | *(required)* | Crop key (must match a crop/preset). |
| `density_plants_m2` | number | plants/m² | ≥ 0 (guidance: 1–400) | *(optional)* | Sowing density. |

### `irrigation` (array of events)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `date` | string | ISO date | `YYYY-MM-DD` | *(required)* | Irrigation date. |
| `mm` | number | mm | ≥ 0 (guidance: 0–100) | *(required)* | Applied water depth. |

### `fertilization` (array of events)

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `date` | string | ISO date | `YYYY-MM-DD` | *(required)* | Application date. |
| `n_kg_ha` | number | kg N/ha | ≥ 0 (guidance: 0–300) | *(optional)* | Nitrogen applied. |
| `p_kg_ha` | number | kg P/ha | ≥ 0 (guidance: 0–150) | *(optional)* | Phosphorus applied. |

---

## Economy — `economy.json`

Input costs and crop price table for the economic ledger. See
[ADR-003: Economic Model](adr/ADR-003-economic-model.md) for scope (credits,
price table, ledger).

- **Schema:** [`economy.json`](https://github.com/gedejong/agrogame/blob/main/agrogame/config/schemas/economy.json)
- **Design doc:** [ADR-003 — Economic Model](adr/ADR-003-economic-model.md)

### Top level

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `input_costs` | object[string→number] | credits per input unit | each ≥ 0 | *(required)* | Cost per unit of each input (e.g. N, P, water, seed). |
| `crop_prices` | object[string→object] | — | — | *(required)* | Per-crop price entry (keyed by crop). |

### `crop_prices[<crop>]`

| Field | Type | Unit | Range / enum | Default | Description |
|---|---|---|---|---|---|
| `base_credits_per_kg` | number | credits/kg | ≥ 0 | *(required)* | Base sale price per kg of harvested product. |
| `seasonal_multipliers` | array[number] | multiplier | exactly 4 items, each ≥ 0 | *(optional)* | Per-season price multipliers (one per season phase). |
