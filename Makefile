PY=poetry run python

.PHONY: plots plots-core plots-microbes plots-events lint test ci

plots-core:
	$(PY) scripts/plot_full_integration.py
	$(PY) scripts/plot_et_timeseries.py --days 120 --out out/et_timeseries.png
	$(PY) scripts/plot_water_timeseries.py --days 120 --out out/water_timeseries.png --pattern seasonal
	$(PY) scripts/plot_nitrogen_timeseries.py --days 120 --out out/nitrogen_timeseries.png --pattern storms
	$(PY) scripts/plot_phosphorus_timeseries.py --days 120 --out out/phosphorus_timeseries.png --pattern seasonal
	$(PY) scripts/plot_phenology_canopy.py --days 120 --out out/phenology_canopy.png --efficiency-out out/phenology_efficiency.png --phase-out out/phenology_phase.png
	$(PY) scripts/plot_roots_timeseries.py --days 120 --out out/roots_timeseries.png
	$(PY) scripts/plot_roots_compare.py --out out/roots_compare.png
	$(PY) scripts/plot_interception_isolation.py --days 60 --out out/interception_isolation.png

plots-microbes:
	$(PY) scripts/plot_microbes_suite.py --days 120 --out-dir out
	$(PY) scripts/plot_microbes_timeseries.py --days 120 --out out/microbes_timeseries.png --pattern seasonal
	$(PY) scripts/plot_microbes_depth.py --days 120 --out out/microbes_depth.png --pattern storms
	$(PY) scripts/plot_microbes_split.py --days 120 --out out/microbes_split.png --pattern seasonal
	$(PY) scripts/plot_microbes_enzyme_depth.py --days 120 --out out/microbes_enzyme_depth.png --pattern constant
	$(PY) scripts/plot_microbes_activity_depth.py --days 120 --out out/microbes_activity_depth.png --pattern seasonal
	$(PY) scripts/plot_microbes_activity_surface.py --days 120 --out out/microbes_activity_surface.png --pattern seasonal
	$(PY) scripts/plot_microbes_diagnostics.py --days 120 --out out/microbes_diagnostics.png --pattern storms

plots-events:
	$(PY) scripts/plot_events_timeline.py --out out/events_timeline.png
	$(PY) scripts/plot_events_heatmap.py --out out/events_heatmap.png
	$(PY) scripts/plot_events_dependencies.py --out out/events_dependencies.png

plots: plots-core plots-microbes plots-events

lint:
	pre-commit run -a

test:
	poetry run pytest -q

ci: lint test


