from __future__ import annotations

from agrogame.sim.builder import (
    generate_rain_evap,
    generate_temp_par,
    build_full_from_preset,
)
from agrogame.soil.loader import load_soil_presets
from pathlib import Path


def test_generate_rain_evap_patterns() -> None:
    r, e = generate_rain_evap(10, 5.0, 2.0, pattern="constant")
    assert len(r) == 10 and len(e) == 10
    assert all(abs(x - 5.0) < 1e-9 for x in r)
    r2, _ = generate_rain_evap(10, 5.0, 2.0, pattern="storms")
    assert any(x > 5.0 for x in r2)


def test_generate_temp_par_patterns() -> None:
    tmins, tmaxs, pars = generate_temp_par(7, 10.0, 20.0, 12.0, pattern="seasonal")
    assert len(tmins) == 7 and len(tmaxs) == 7 and len(pars) == 7


def test_build_full_from_preset_smoke() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    orch = build_full_from_preset("loam_temperate")
    assert orch.profile.name == lib.soils["loam_temperate"].name
