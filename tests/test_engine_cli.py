from __future__ import annotations

from pathlib import Path

from agrogame.sim import SimulationEngine
from agrogame.soil.loader import load_soil_presets


def test_engine_runs_three_days(tmp_path: Path) -> None:
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    weather = Path("data/weather/sample.csv")
    eng = SimulationEngine(profile, str(weather))
    eng.schedule_irrigation(1, 5.0)
    res = eng.run_season()
    assert res.days_processed >= 3
    assert res.finished is True


def test_cli_stub_prints(capsys) -> None:
    from agrogame.cli import main

    code = main()
    out = capsys.readouterr().out
    assert code == 0
    assert "AgroGame simulation CLI stub" in out


def test_cli_engine_subcommand_runs(monkeypatch, capsys) -> None:
    from agrogame.cli import main
    import sys

    argv = [
        "simulate",
        "engine",
        "--profile",
        "loam_temperate",
        "--weather-file",
        "data/weather/sample.csv",
        "--speed",
        "1",
        "--irrigate",
        "1",
        "2.0",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    code = main()
    out = capsys.readouterr().out
    assert code == 0
    assert "Days processed" in out


def test_benchmarks_mode_min_cov() -> None:
    # Lightweight smoke to include engine path in bench profile
    from agrogame.sim.engine import SimulationEngine
    from agrogame.soil.loader import load_soil_presets

    lib = load_soil_presets(Path("soils/presets.yaml"))
    eng = SimulationEngine(lib.soils["loam_temperate"], Path("data/weather/sample.csv"))
    # Run a single step to exercise code paths covered in bench job
    eng.set_speed(1)
    eng.advance_day()


def test_cli_run_subcommand_runs(monkeypatch) -> None:
    from agrogame.cli import main
    import sys

    argv = [
        "simulate",
        "run",
        "--profile",
        "loam_temperate",
        "--weather-file",
        "data/weather/sample.csv",
        "--days",
        "2",
    ]
    monkeypatch.setattr(sys, "argv", argv)
    code = main()
    assert code == 0
