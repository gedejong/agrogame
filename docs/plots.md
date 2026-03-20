### Diagnostics & Plots

This page documents the migration of plotting utilities from `scripts/` into the
package module `agrogame.plots` and describes how to use and extend them.

#### What changed

- We introduced a new package: `agrogame/plots/`.
- The full integration plot previously implemented in `scripts/plot_full_integration.py`
  has been ported to `agrogame/plots/full_integration.py`.
- The original script now acts as a thin wrapper that imports and calls `main()`
  from `agrogame.plots.full_integration` to maintain CLI compatibility.
- Coverage was updated to omit `agrogame/plots/*` from unit-test coverage accounting,
  since these modules are primarily visualization entrypoints.

#### Where to find things

- Module: `agrogame/plots/full_integration.py`
  - Generates `out/full_integration.png` and `out/full_integration_timeseries.csv`.
  - Automatically runs `scripts/check_expectations.py` to produce
    `out/expectations_full_integration.md` after plotting.
  - Subscribes to water and nutrient stress events for realistic overlays.
  - Uses event-aggregated evaporation/transpiration for flux panels.

- Script wrapper: `scripts/plot_full_integration.py`
  - Delegates to `agrogame.plots.full_integration.main()`.
  - Keeps existing CLI usage unchanged.

#### Key parameters

- `--days`: number of simulation days to plot.
- `--profile`: soil profile key (see `soils/presets.yaml`).
- `--n-demand` and `--p-demand`: base plant N/P demand; scaled by biomass increment.
- Weather:
  - Use local weather file via `scripts/_weather_cli.py` args, or
  - `--alt-weather` to synthesize sinusoidal weather for demos.

#### Expectations checks

The plot module writes a CSV and then runs `scripts/check_expectations.py` to
validate high-level expectations. The report is written to
`out/expectations_full_integration.md`. Current checks include:

- Stress bounds in [0, 1]
- Water coherence (low stress implies low actual/potential transpiration)
- P-stress correlates with available P (with robust fallbacks)
- ET exceedance diagnostics (E+T vs ET0)
- LAI shape and optional harvest diagnostics

#### Why this refactor

- Apply the project’s quality gates (lint/type checks) to plotting logic.
- Eliminate circular-imports common in ad-hoc scripts.
- Enable reuse of plotting components by the dashboard and tests.

#### Extending

- Add new plot entrypoints under `agrogame/plots/` and expose a small CLI `main()`.
- Keep script wrappers in `scripts/` minimal (import + call) for backwards
  compatibility.
- Prefer event subscriptions for time-series aggregation to avoid tight coupling.


