"""Tests covering missing lines in agrogame/weather/loader.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agrogame.weather.loader import _opt_float, _parse_date, load_weather


# ---------------------------------------------------------------------------
# _parse_date edge cases (lines 21-23)
# ---------------------------------------------------------------------------


def test_parse_date_slash_format() -> None:
    """Cover line 21-22: second format attempt."""
    d = _parse_date("2024/06/15")
    assert d.year == 2024 and d.month == 6 and d.day == 15


def test_parse_date_dmy_format() -> None:
    """Cover line 21-23: third format attempt."""
    d = _parse_date("15-06-2024")
    assert d.year == 2024 and d.month == 6 and d.day == 15


def test_parse_date_unsupported() -> None:
    """Cover line 23: unsupported format raises ValueError."""
    with pytest.raises(ValueError, match="Unsupported date format"):
        _parse_date("June 15, 2024")


# ---------------------------------------------------------------------------
# load_weather unsupported extension (line 31)
# ---------------------------------------------------------------------------


def test_load_weather_unsupported_extension(tmp_path: Path) -> None:
    """Cover line 31: unsupported file extension."""
    p = tmp_path / "weather.xml"
    p.write_text("<data/>")
    with pytest.raises(ValueError, match="Unsupported weather file type"):
        load_weather(p)


# ---------------------------------------------------------------------------
# _load_json with validate_data fallback (lines 63-66)
# ---------------------------------------------------------------------------


def test_load_json_with_validation_fallback(tmp_path: Path) -> None:
    """Cover lines 63-66: JSON that doesn't match schema but loads ok."""
    p = tmp_path / "w.json"
    data = [
        {"date": "2024-06-01", "tmin_c": 10, "tmax_c": 22},
        {"date": "2024-06-02", "tmin_c": 11, "tmax_c": 24},
    ]
    p.write_text(json.dumps(data))
    series = load_weather(p)
    assert len(series.records) == 2


# ---------------------------------------------------------------------------
# _load_json parse error (lines 83-84)
# ---------------------------------------------------------------------------


def test_load_json_parse_error(tmp_path: Path) -> None:
    """Cover lines 83-84: bad record in JSON array."""
    p = tmp_path / "w.json"
    data = [{"date": "2024-06-01", "tmin_c": "bad", "tmax_c": 22}]
    p.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="JSON parse error"):
        load_weather(p)


# ---------------------------------------------------------------------------
# _opt_float edge cases (lines 94-95, 98)
# ---------------------------------------------------------------------------


def test_opt_float_invalid_value() -> None:
    """Cover lines 94-95: non-numeric raises ValueError."""
    with pytest.raises(ValueError, match="Invalid numeric value"):
        _opt_float("not_a_number")


def test_opt_float_sentinel_minus999() -> None:
    """Cover line 98: sentinel -999 returns None."""
    assert _opt_float(-999) is None
    assert _opt_float(-999.0) is None
    assert _opt_float("-999") is None


def test_opt_float_normal() -> None:
    assert _opt_float("12.5") == 12.5
    assert _opt_float(None) is None
    assert _opt_float("") is None


# ---------------------------------------------------------------------------
# CSV with parse error (lines 83-84 equivalent for CSV)
# ---------------------------------------------------------------------------


def test_load_csv_parse_error(tmp_path: Path) -> None:
    """Cover CSV parse error line (line 53-54 in _load_csv)."""
    p = tmp_path / "w.csv"
    p.write_text("date,tmin_c,tmax_c\n" "2024-06-01,bad,22\n")
    with pytest.raises(ValueError, match="CSV parse error"):
        load_weather(p)


# ---------------------------------------------------------------------------
# CSV with net_radiation and precip (full fields)
# ---------------------------------------------------------------------------


def test_load_csv_full_fields(tmp_path: Path) -> None:
    """Cover various optional field parsing in _load_csv."""
    p = tmp_path / "w.csv"
    p.write_text(
        "date,tmin_c,tmax_c,rh_pct,wind_m_s,rs_mj_m2,rn_mj_m2,albedo,precip_mm\n"
        "2024-06-01,10,22,60,2.5,18,14,0.23,5\n"
    )
    series = load_weather(p)
    rec = series.records[0]
    assert rec.net_radiation_mj_m2 == 14.0
    assert rec.precip_mm == 5.0
    assert rec.albedo == 0.23
