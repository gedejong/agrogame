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
- The dashboard uses a lightweight heuristic for water stress for display only
- Data sources align with the event-driven modules; no core logic is modified

