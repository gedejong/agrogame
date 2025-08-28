from __future__ import annotations

import json
from datetime import date
from typing import Any

from agrogame.weather.loader import load_weather_auto


class _FakeResp:
    def __init__(self, payload: dict[str, Any]):
        self._data = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeResp":  # noqa: D401
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        return None

    def read(self) -> bytes:  # noqa: D401
        return self._data


def test_power_auto_fetch_monkeypatched(monkeypatch) -> None:
    # Prepare minimal NASA POWER-like payload for a single day
    day_key = "20240601"
    payload = {
        "properties": {
            "parameter": {
                "T2M_MAX": {day_key: 25.0},
                "T2M_MIN": {day_key: 12.0},
                "RH2M": {day_key: 60.0},
                "WS10M": {day_key: 2.5},
                "ALLSKY_SFC_SW_DWN": {day_key: 18.0},
            }
        }
    }

    def _fake_urlopen(url: str, timeout: int = 60):  # noqa: D401
        return _FakeResp(payload)

    import urllib.request as _u

    monkeypatch.setattr(_u, "urlopen", _fake_urlopen)

    series = load_weather_auto(52.0, 5.0, date(2024, 6, 1), date(2024, 6, 1))
    assert len(series.records) == 1
    rec = series.records[0]
    # Net radiation derived from shortwave with albedo 0.23 => 18*(1-0.23)
    assert rec.net_radiation_mj_m2 == 18.0 * (1.0 - 0.23)
