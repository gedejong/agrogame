from __future__ import annotations

from pathlib import Path
import pytest

from agrogame.weather import load_weather


def test_csv_loader_rejects_missing_columns(tmp_path: Path) -> None:
    p = tmp_path / "bad.csv"
    p.write_text("date,tmax_c\n2024-06-01,22\n")
    with pytest.raises(ValueError):
        _ = load_weather(p)
