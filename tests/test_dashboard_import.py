"""Dashboard façade tests (#309, ADR-011).

The original smoke test (preserved below as ``test_import_dashboard_module``)
guarded against import-time side effects. After #309 the dashboard
consumes the engine exclusively through ``agrogame.api.dashboard_facade``;
the new ``test_dashboard_facade_one_day_end_to_end`` drives one
simulated day through the façade and asserts the history-dict shape so
that dropping an event subscriber surfaces immediately rather than as
a silent blank chart in production.
"""

from __future__ import annotations

import importlib
import sys
from datetime import date

import pytest


@pytest.mark.skipif(sys.version_info < (3, 10), reason="dashboard targets Python 3.10+")
def test_import_dashboard_module() -> None:
    """Smoke: dashboard package imports cleanly (preserved from pre-#309)."""
    # Skip if optional dashboard extras are not available in this environment
    pytest.importorskip("plotly")
    pytest.importorskip("streamlit")
    mod = importlib.import_module("agrogame.dashboard.app")
    assert hasattr(mod, "main")


# Keys the dashboard relies on; if a subscriber is dropped, the
# corresponding key never gets appended to and the dashboard renders
# blank. This test catches that at PR time instead of in production.
_EXPECTED_HISTORY_KEYS = (
    "day",
    "lai",
    "biomass_g_m2",
    "biomass_inc_g_m2",
    "theta_layers",
    "no3_layers",
    "nh4_layers",
    "root_depth_cm",
    "stage",
    "rain_mm",
    "tmin_c",
    "tmax_c",
    "tmean_c",
    "et0_mm",
    "et0_pt_mm",
    "evap_mm",
    "transp_mm",
    "vpd_kpa",
    "stomatal",
    "water_stress",
    "n_stress",
    "p_stress",
    "n_total_kgha",
    "micro_c_total",
    "micro_n_total",
    "micro_fb_avg",
    "enzyme_cellulase_c",
    "enzyme_protease_c",
    "enzyme_phosphatase_c",
    "enzyme_urease_c",
    "micro_activity_avg",
    "micro_activity_layers",
)


def test_dashboard_facade_one_day_end_to_end() -> None:
    """End-to-end one-day run through the façade — covers #309 AC #7.

    Exercises ``DashboardSimulationRun`` directly (no file I/O, no
    Streamlit) so the test passes on bare ``pip install`` without the
    optional ``-E dashboard`` extras. Asserts the history dict has every
    key the dashboard charts read — dropping a subscriber would leave
    one of these empty.
    """
    from agrogame.api.dashboard_facade import (
        DashboardSimulationRun,
        WeatherRecord,
        load_soil_profile,
        make_drivers,
    )

    profile = load_soil_profile()
    run = DashboardSimulationRun(profile)

    rec = WeatherRecord(
        day=date(2026, 5, 1),
        tmin_c=10.0,
        tmax_c=22.0,
        relative_humidity_pct=60.0,
        wind_m_s=2.0,
        shortwave_mj_m2=15.0,
        net_radiation_mj_m2=12.0,
        albedo=0.23,
        precip_mm=2.0,
    )

    et0, et0_pt, par, _rn, tmean, vpd = run.compute_reference_et(rec)
    run.history["et0_mm"].append(et0)
    run.history["et0_pt_mm"].append(et0_pt)
    run.reset_daily_counters()
    run.step_day(
        make_drivers(rec.precip_mm or 0.0),
        tmin_c=rec.tmin_c,
        tmax_c=rec.tmax_c,
        par_mj_m2=par,
    )
    ws, stomatal = run.calc_stress(
        vpd=vpd, lai=run.lai, transp_mm=run.agg.transp_mm, et0_mm=et0
    )
    run.append_day_summary(et0=et0, water_stress=ws, vpd=vpd, stomatal=stomatal)
    run.append_micro_activity(day_index=0)
    run.history["day"].append(rec.day)
    run.history["lai"].append(run.lai)
    run.append_biomass_and_interception(par=par)
    run.append_root_and_stage()
    run.append_layers(day_index=0)
    run.append_weather(rain=rec.precip_mm or 0.0, rec=rec, tmean=tmean)
    run.append_n_total()
    run.append_microbes()
    run.append_enzyme_groups()

    # `et0_mm` and `et0_pt_mm` are appended once outside append_day_summary
    # (see _run_simulation), and `et0_mm` is appended again inside it — a
    # pre-existing duplicate in the dashboard's per-day book-keeping that
    # downstream charts have always tolerated. Out of scope for #309 to fix.
    keys_with_duplicate_first = {"et0_mm"}

    for key in _EXPECTED_HISTORY_KEYS:
        assert key in run.history, f"history missing key {key!r} — subscriber dropped?"
        val = run.history[key]
        if key.endswith("_layers"):
            assert len(val) == len(profile.layers), f"{key} per-layer length wrong"
            assert len(val[0]) == 1, f"{key}[0] should have 1 entry, has {len(val[0])}"
        else:
            expected = 2 if key in keys_with_duplicate_first else 1
            assert (
                len(val) == expected
            ), f"{key} should have {expected} entr(y/ies), has {len(val)}"


def test_dashboard_does_not_import_engine_internals() -> None:
    """Regression guard for the layering invariant (#309, ADR-011).

    Asserts that no module under ``agrogame.dashboard`` imports from
    the engine packages — the import-linter contract enforces this in
    CI, but having a fast unit-test version means contributors see the
    failure immediately on `pytest -k dashboard` rather than after a
    full Quality run.
    """
    import pkgutil
    from pathlib import Path

    forbidden_prefixes = (
        "from agrogame.soil",
        "from agrogame.plant",
        "from agrogame.weather",
        "from agrogame.atmosphere",
        "from agrogame.sim",
        "import agrogame.soil",
        "import agrogame.plant",
        "import agrogame.weather",
        "import agrogame.atmosphere",
        "import agrogame.sim",
    )

    import agrogame.dashboard

    dashboard_dir = Path(agrogame.dashboard.__file__).parent
    offenders: list[tuple[str, int, str]] = []
    for mod_info in pkgutil.walk_packages(
        [str(dashboard_dir)], prefix="agrogame.dashboard."
    ):
        py_path = dashboard_dir / (
            mod_info.name.removeprefix("agrogame.dashboard.").replace(".", "/") + ".py"
        )
        if not py_path.exists():
            continue
        for i, line in enumerate(py_path.read_text().splitlines(), start=1):
            stripped = line.strip()
            if any(stripped.startswith(p) for p in forbidden_prefixes):
                offenders.append((mod_info.name, i, stripped))

    assert not offenders, (
        "Dashboard imports engine internals (must consume via "
        "agrogame.api.dashboard_facade per ADR-011):\n  "
        + "\n  ".join(f"{m}:{i} {line}" for m, i, line in offenders)
    )
