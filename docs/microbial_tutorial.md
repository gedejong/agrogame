### Microbial module tutorial

This tutorial shows how to run the microbes visualization suite, interpret plots, and tweak parameters.

#### Run the suite

```bash
poetry run python scripts/plot_microbes_suite.py --profile loam_temperate --days 120 --out-dir out
```

Generated images:
- `microbes_timeseries.png`: total microbial C/N over time
- `microbes_depth.png`: time–depth heatmaps of C and N
- `microbes_split.png`: fungal vs bacterial depth split
- `microbes_enzyme_depth.png`: enzyme production costs by depth
- `microbes_activity_depth.png`: activity index by depth
- `microbes_diagnostics.png`: WFPS, pH, substrate diagnostics
- `microbes_activity_surface.png`: activity response (T × WFPS) at pH 6.8

#### Interpret key patterns
- Activity increases with moderate WFPS, near-neutral pH, and favorable T.
- Substrate availability and quality (near roots) boost growth (Monod kinetics).
- Fungal:bacterial fraction adapts with moisture and pH; enzymes incur C cost.

#### Tweak parameters
You can override microbial parameters in the timeseries script:

```bash
poetry run python scripts/plot_microbes_timeseries.py \
  --profile loam_temperate --days 120 \
  --fb-adjust 0.02 \
  --enz-weights "cellulase=0.3,protease=0.3,phosphatase=0.3,urease=0.1"
```

#### Notes
- Root-driven substrate and priming are smoothed to avoid day-to-day steps.
- Root distributions are continuous across layer boundaries for smoother depth signals.


