from __future__ import annotations

from pathlib import Path
import subprocess


def test_compare_series_cli_smoke(tmp_path: Path):
    obs = tmp_path / "obs.csv"
    sim = tmp_path / "sim.csv"
    obs.write_text("date,val\n2024-06-01,0\n2024-06-02,1\n2024-06-03,2\n")
    sim.write_text("date,val\n2024-06-01,0\n2024-06-02,2\n2024-06-03,4\n")
    res = subprocess.run(
        [
            "poetry",
            "run",
            "python",
            "scripts/compare_series.py",
            "--obs",
            str(obs),
            "--sim",
            str(sim),
            "--key",
            "date",
            "--obs-col",
            "val",
            "--sim-col",
            "val",
            "--tol",
            "1.0",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "N=3" in res.stdout
