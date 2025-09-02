from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from agrogame.weather import load_weather_auto


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def main() -> int:
    scenarios_path = Path("tests/data/benchmarks/scenarios.yaml")
    cfg = yaml.safe_load(scenarios_path.read_text())
    out_dir = Path("tests/data/benchmarks/fullseason")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, sc in cfg.items():
        lat = float(sc["lat"])  # type: ignore[index]
        lon = float(sc["lon"])  # type: ignore[index]
        start = _parse_date(str(sc["start"]))
        end = _parse_date(str(sc["end"]))
        series = load_weather_auto(lat, lon, start, end)
        out = out_dir / f"{name}.csv"
        # Write POWER-like CSV compatible with load_weather
        with out.open("w") as f:
            f.write("date,tmin_c,tmax_c,rh_pct,wind_m_s,rs_mj_m2,precip_mm,rn_mj_m2\n")
            for r in series.records:
                f.write(f"{r.day.isoformat()},{r.tmin_c},{r.tmax_c},")
                f.write(f"{r.relative_humidity_pct or ''},{r.wind_m_s or ''},")
                rs = r.shortwave_mj_m2 or ""
                pmm = r.precip_mm or ""
                rn = r.net_radiation_mj_m2 or ""
                f.write(f"{rs},{pmm},{rn}\n")
        print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
