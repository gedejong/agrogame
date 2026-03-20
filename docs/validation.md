### Validation metrics and benchmarks

We validate simulations against benchmark scenarios using:

- R² (Pearson r²), RMSE, MAE, MBE
- NSE (Nash–Sutcliffe), Willmott d, coverage within tolerance
- Phenology timing error (days)

Targets (typical):
- Yield within 10% of benchmark
- Phenology within 5 days to flowering/maturity windows
- Biomass time-series quality: R² > 0.9, NSE > 0.8

How to run:
```bash
poetry run pytest -k benchmarks -q
# Compare two CSV series
poetry run python scripts/compare_series.py --obs tests/data/observed_biomass.csv --sim out/built_crops.yaml --key date --obs-col biomass --sim-col biomass
```


