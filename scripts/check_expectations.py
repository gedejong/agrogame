from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd
from io import StringIO


def check_monotonic(series: pd.Series, name: str) -> Tuple[bool, str]:
    inc = (series.diff().fillna(0) >= -1e-9).all()
    return inc, f"{name} monotonic non-decreasing"


def check_lai_shape(
    series: pd.Series,
    peak_tail_days: int = 10,
    eps: float = 0.05,
    smooth_window: int = 3,
) -> Tuple[bool, str, Dict[str, float]]:
    diagnostics: Dict[str, float] = {}
    if series.empty:
        return True, "LAI increases then plateaus/declines", diagnostics

    # Smooth small day-to-day noise
    s = series.rolling(window=max(1, smooth_window), min_periods=1, center=False).mean()

    max_idx = int(s.idxmax())
    diagnostics["lai_max_day_index"] = float(max_idx)
    diagnostics["lai_max_value"] = float(
        s.iloc[max_idx - 1] if 0 < max_idx <= len(s) else s.max()
    )

    # If peak is within the last N days, consider season not finished;
    # treat as soft-pass
    last_index = int(s.index.max())
    if last_index - max_idx < peak_tail_days:
        return True, "LAI peak near end (season likely not finished)", diagnostics

    left_inc = (s.iloc[: max_idx + 1].diff().fillna(0) >= -eps).all()
    right_dec = (s.iloc[max_idx:].diff().fillna(0) <= eps).all()
    ok = bool(left_inc and right_dec)
    return ok, "LAI increases then plateaus/declines", diagnostics


def check_irrigation_stress(
    ts: pd.DataFrame,
    irr_days: List[int],
    pre_window: int = 3,
    post_window: int = 5,
    min_improvement: float = 0.0,
    improve_if_pre_below: float | None = None,
) -> Tuple[List[Tuple[bool, str]], List[Dict[str, float]]]:
    results: List[Tuple[bool, str]] = []
    diags: List[Dict[str, float]] = []
    for d in irr_days:
        pre = ts.loc[ts["day"].between(d - pre_window, d - 1), "water_stress"].mean()
        post = ts.loc[ts["day"].between(d + 1, d + post_window), "water_stress"].mean()
        delta = float(post - pre) if pd.notna(pre) and pd.notna(post) else float("nan")
        gated = False
        if improve_if_pre_below is not None and pd.notna(pre):
            gated = float(pre) < float(improve_if_pre_below)
        ok = (
            pd.notna(pre)
            and pd.notna(post)
            and ((delta >= min_improvement - 1e-6) if gated else True)
        )
        if gated:
            label = (
                f"Stress improves by >= {min_improvement:.2f} after irrigation day {d}"
            )
        elif improve_if_pre_below is not None:
            label = (
                "Stress non-required (pre >= "
                f"{improve_if_pre_below}) after irrigation day {d}"
            )
        else:
            label = (
                f"Stress improves by >= {min_improvement:.2f} after irrigation day {d}"
            )
        results.append((bool(ok), label))
        diags.append(
            {
                "day": float(d),
                "pre_mean": float(pre) if pd.notna(pre) else float("nan"),
                "post_mean": float(post) if pd.notna(post) else float("nan"),
                "delta": delta,
                "gated": float(1.0 if gated else 0.0),
            }
        )
    return results, diags


def check_et_bounded(
    ts: pd.DataFrame,
    max_exceed_fraction: float = 0.10,
    exclude_lai_below: float | None = None,
) -> Tuple[bool, str, Dict[str, float]]:
    diagnostics: Dict[str, float] = {}
    scope = ts
    if exclude_lai_below is not None and "lai" in ts.columns:
        scope = ts.loc[ts["lai"] >= exclude_lai_below]
        diagnostics["rows_considered"] = float(scope.shape[0])

    margin = (scope["evap_mm"] + scope["transp_mm"]) - scope["et0_mm"]
    frac_exceed = float((margin > 1e-3).mean()) if len(margin) else 0.0
    diagnostics["fraction_exceed"] = frac_exceed
    diagnostics["max_margin"] = float(margin.max()) if len(margin) else 0.0
    diagnostics["mean_margin"] = float(margin.mean()) if len(margin) else 0.0
    return (
        frac_exceed < max_exceed_fraction,
        f"Actual ET exceedance fraction < {max_exceed_fraction:.2f}",
        diagnostics,
    )


def main() -> None:
    p = argparse.ArgumentParser(description="Check expectations against timeseries CSV")
    p.add_argument("--timeseries", type=Path, required=True)
    p.add_argument(
        "--irrigate", action="append", help="Irrigation as 'day,mm'", default=[]
    )
    p.add_argument("--harvest", type=int, help="Harvest day (optional)")
    p.add_argument("--out", type=Path, default=Path("out/expectations.md"))
    # Tuning
    p.add_argument("--stress-pre", type=int, default=3)
    p.add_argument("--stress-post", type=int, default=10)
    p.add_argument("--stress-min-improvement", type=float, default=0.0)
    p.add_argument("--et-max-exceed-frac", type=float, default=0.10)
    p.add_argument("--et-exclude-lai-below", type=float, default=0.2)
    p.add_argument("--lai-peak-tail-days", type=int, default=20)
    p.add_argument("--lai-eps", type=float, default=0.1)
    p.add_argument("--lai-smooth", type=int, default=5)
    p.add_argument("--stress-improve-if-pre-below", type=float, default=0.7)
    p.add_argument(
        "--fail-on-any",
        action="store_true",
        help="Exit non-zero if any check fails (for CI gating)",
    )
    args = p.parse_args()

    ts = pd.read_csv(args.timeseries)

    checks: List[Tuple[bool, str]] = []
    diagnostics_sections: List[str] = []

    # Expectations
    # Biomass monotonicity only up to harvest if provided
    biomass_series = ts["biomass_g_m2"]
    if args.harvest is not None:
        mask = ts["day"] <= int(args.harvest)
        ok_biomass, name_biomass = check_monotonic(
            biomass_series[mask], "Biomass (pre-harvest)"
        )
    else:
        ok_biomass, name_biomass = check_monotonic(biomass_series, "Biomass")
    checks.append((ok_biomass, name_biomass))

    ok_et, name_et, diag_et = check_et_bounded(
        ts,
        max_exceed_fraction=args.et_max_exceed_frac,
        exclude_lai_below=args.et_exclude_lai_below,
    )
    checks.append((ok_et, name_et))

    ok_lai, name_lai, diag_lai = check_lai_shape(
        ts["lai"],
        peak_tail_days=args.lai_peak_tail_days,
        eps=args.lai_eps,
        smooth_window=args.lai_smooth,
    )
    checks.append((ok_lai, name_lai))

    irr_days = [int(s.split(",")[0]) for s in (args.irrigate or [])]
    irr_results, irr_diags = check_irrigation_stress(
        ts,
        irr_days,
        pre_window=args.stress_pre,
        post_window=args.stress_post,
        min_improvement=args.stress_min_improvement,
        improve_if_pre_below=args.stress_improve_if_pre_below,
    )
    checks.extend(irr_results)

    # Diagnostics text assembly
    # ET vs ET0 exceedance details
    margin_full = (ts["evap_mm"] + ts["transp_mm"]) - ts["et0_mm"]
    ts_et = ts.copy()
    ts_et["et_margin"] = margin_full
    top_exceed = ts_et.sort_values("et_margin", ascending=False).head(10)
    buf_top = StringIO()
    top_exceed[["day", "evap_mm", "transp_mm", "et0_mm", "lai", "et_margin"]].to_csv(
        buf_top, index=False
    )
    diagnostics_sections.append(
        (
            "## ET exceedance diagnostics\n\n"
            f"- fraction_exceed (LAI>={args.et_exclude_lai_below}): "
            f"{diag_et.get('fraction_exceed', 0.0):.3f}\n"
            f"- max_margin: {diag_et.get('max_margin', 0.0):.3f}\n"
            f"- mean_margin: {diag_et.get('mean_margin', 0.0):.3f}\n\n"
            "Top 10 days by ET margin (E+T - ET0):\n\n"
            "```csv\n" + buf_top.getvalue() + "```\n"
        )
    )

    # LAI shape diagnostics
    diagnostics_sections.append(
        (
            "## LAI diagnostics\n\n"
            f"- lai_max_day_index: {diag_lai.get('lai_max_day_index', float('nan'))}\n"
            f"- lai_max_value: {diag_lai.get('lai_max_value', float('nan'))}\n"
        )
    )

    # Irrigation pre/post diagnostics
    buf_irr = StringIO()
    pd.DataFrame(irr_diags).to_csv(buf_irr, index=False)
    diagnostics_sections.append(
        (
            "## Irrigation impact diagnostics\n\n"
            "Pre/Post window means and deltas by irrigation day:\n\n"
            "```csv\n" + buf_irr.getvalue() + "```\n"
        )
    )

    # Harvest-aware check and diagnostics
    if args.harvest is not None:
        after = ts.loc[ts["day"] > args.harvest]
        before = ts.loc[ts["day"] <= args.harvest]
        if not after.empty and "lai" in ts.columns:
            drop = before["lai"].iloc[-1] - after["lai"].head(7).mean()
            ok_harvest = drop > 0.5 * max(1.0, before["lai"].max())
            checks.append((bool(ok_harvest), "LAI drops after harvest"))
            diagnostics_sections.append(
                (
                    "## Harvest diagnostics\n\n"
                    f"- harvest_day: {args.harvest}\n"
                    f"- lai_before_last: {before['lai'].iloc[-1]:.3f}\n"
                    f"- lai_after_mean_7d: {after['lai'].head(7).mean():.3f}\n"
                    f"- lai_drop: {drop:.3f}\n"
                )
            )
        else:
            diagnostics_sections.append(
                (
                    "## Harvest diagnostics\n\n"
                    "No post-harvest window available; skipping LAI drop check.\n"
                )
            )

    # Write report
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as f:
        f.write("# Expectations Report\n\n")
        for ok, name in checks:
            f.write(f"- [{'x' if ok else ' '}] {name}\n")
        f.write("\n")
        # Append a quick metrics table
        f.write("## Summary\n\n")
        desc = ts.describe()
        try:
            f.write(desc.to_markdown(index=True))
        except Exception:
            buf = StringIO()
            desc.to_csv(buf)
            f.write("\n```csv\n")
            f.write(buf.getvalue())
            f.write("```\n")
        f.write("\n\n")
        for section in diagnostics_sections:
            f.write(section)
            f.write("\n")

    # Console summary
    passed = sum(1 for ok, _ in checks if ok)
    total = len(checks)
    print(f"Checks passed: {passed}/{total}. Report: {args.out}")
    if args.fail_on_any and passed < total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
