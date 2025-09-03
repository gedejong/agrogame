### Dashboard (Experimental)

The Streamlit dashboard provides an interactive view of simulation outputs:

- Soil tab: per-layer volumetric water content (θ), NO3 and NH4 time series
- Crop tab: biomass over time, root depth, current phenology stage, water stress
- Management: summary of irrigation and fertilizer actions applied this run
- Weather: Tmin/Tmax, rainfall and ET0 (Penman–Monteith)

Run locally (requires extras):

```bash
poetry install -E dashboard
poetry run dashboard
```

Notes:
- The dashboard uses lightweight display heuristics for some indicators. Core simulation logic is unchanged.
- Phosphorus (P) indicator: not modeled yet. The UI shows P as N/A. Roadmap: add P pools and uptake model; update indicator thresholds accordingly.
- Nutrient traffic lights: N status is derived from mineral N pools as a proxy; thresholds are documented below.
- Yield projection: simple harvest-index estimate with a ±20% band interpreted as a rough CI for visualization.
- High-contrast mode: toggle in the sidebar to improve accessibility and readability.
- Root animation: use the "Play root animation" button in Crop tab; playback scrubs to the current global day.

Preview:

![Dashboard Screenshot](images/dashboard.png)

#### Indicator details

- Growth stage progress bar: computed from GDD versus stage thresholds from the phenology module.
- Nutrient traffic lights (N): green ≥ 0.8, amber 0.5–0.8, red < 0.5 of proxy sufficiency.
- Yield projection: yield_t_ha = (biomass_kg_ha / 1000) × HI; defaults HI=0.5; CI shown as 80–120% of point estimate.

#### Exports

- CSV exports available for weather, soil moisture by layer, biomass, and root depth from their respective tabs.

#### Accessibility

- High-contrast mode affects color palette for soil moisture and templates for charts to improve contrast.

