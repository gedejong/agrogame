from __future__ import annotations

from pathlib import Path

from agrogame.weather import load_weather, WeatherSeries
from agrogame.weather.utils import vpd_kpa, net_radiation_from_shortwave


def test_csv_loader_parses_sample(tmp_path: Path) -> None:
    p = tmp_path / "w.csv"
    p.write_text(
        "date,tmin_c,tmax_c,rh_pct,wind_m_s,rs_mj_m2,albedo\n"
        "2024-06-01,10,22,60,2.5,18,0.23\n"
        "2024-06-02,11,24,55,3.0,20,0.23\n"
    )
    series = load_weather(p)
    assert isinstance(series, WeatherSeries)
    assert len(series.records) == 2
    assert series.records[0].tmax_c == 22.0


def test_json_loader_parses_sample(tmp_path: Path) -> None:
    p = tmp_path / "w.json"
    p.write_text(
        "[\n"
        ' {"date": "2024-06-01", "tmin_c": 10, "tmax_c": 22, "rh_pct": 60},\n'
        ' {"date": "2024-06-02", "tmin_c": 11, "tmax_c": 24, "rh_pct": 55}\n'
        "]\n"
    )
    series = load_weather(p)
    assert len(series.records) == 2
    assert series.records[1].tmin_c == 11.0


def test_derivations_vpd_and_rn() -> None:
    vpd = vpd_kpa(temp_mean_c=20.0, relative_humidity_pct=50.0)
    assert vpd > 0
    rn = net_radiation_from_shortwave(rs_mj_m2=20.0, albedo=0.23, lw_net_mj_m2=2.0)
    assert rn > 0
