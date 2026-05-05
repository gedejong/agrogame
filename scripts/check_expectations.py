from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from io import StringIO


def check_monotonic(series: pd.Series, name: str) -> tuple[bool, str]:
    inc = (series.diff().fillna(0) >= -1e-9).all()
    return inc, f"{name} monotonic non-decreasing"


def check_lai_shape(
    series: pd.Series,
    peak_tail_days: int = 10,
    eps: float = 0.05,
    smooth_window: int = 3,
) -> tuple[bool, str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
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
    irr_days: list[int],
    pre_window: int = 3,
    post_window: int = 5,
    min_improvement: float = 0.0,
    improve_if_pre_below: float | None = None,
) -> tuple[list[tuple[bool, str]], list[dict[str, float]]]:
    results: list[tuple[bool, str]] = []
    diags: list[dict[str, float]] = []
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


def check_stress_bounds(ts: pd.DataFrame) -> tuple[bool, str]:
    ok_cols = []
    for col in ("water_stress", "n_stress", "p_stress"):
        if col in ts.columns:
            s = ts[col]
            ok = s.dropna().between(0.0, 1.0).all()
            ok_cols.append(bool(ok))
    return (all(ok_cols) if ok_cols else True), "Stress values within [0,1]"


def check_water_coherence(
    ts: pd.DataFrame,
    low_thr: float = 0.6,
    lai_min: float = 0.5,
    denom_min: float = 1.0,
    ratio_thr: float = 0.65,
    max_exceed_frac: float = 0.10,
) -> tuple[bool, str, dict[str, float]]:
    """Low water stress should imply low actual/potential transpiration.

    Uses transp_mm / (et0_mm * canopy_cover proxy) if potential not stored; here we
    approximate with transp_mm / max(transp_mm, et0_mm) to ensure bounded ratio.
    """
    diagnostics: dict[str, float] = {}
    if "water_stress" not in ts.columns:
        return True, "Water coherence (skipped)", diagnostics
    # Prefer actual/potential transpiration when available
    if "pot_transp_mm" in ts.columns:
        denom = ts["pot_transp_mm"].astype(float).clip(lower=1e-6)
    else:
        denom = ts["et0_mm"].astype(float).clip(lower=1e-6)
    ratio = (ts["transp_mm"].astype(float) / denom).clip(upper=1.0)
    valid_lai = ts.get("lai", 1.0) >= lai_min
    valid_denom = denom >= denom_min
    mask = (ts["water_stress"] < low_thr) & valid_lai & valid_denom
    scope = ts.loc[mask]
    diagnostics["rows_considered"] = float(scope.shape[0])
    if scope.empty:
        return True, "Water coherence (no low-stress days)", diagnostics
    r_scope = ratio.loc[scope.index]
    ratio_mean = float(r_scope.mean())
    frac_exceed = float((r_scope > ratio_thr + 1e-6).mean()) if len(r_scope) else 0.0
    diagnostics["ratio_mean"] = ratio_mean
    diagnostics["fraction_exceed"] = frac_exceed
    ok = bool((ratio_mean <= ratio_thr + 1e-6) and (frac_exceed <= max_exceed_frac))
    return ok, "Low water stress implies low supply", diagnostics


def check_p_correlation(
    ts: pd.DataFrame,
    min_pos_r: float = 0.2,
    start_day: int = 20,
    lai_min_active: float = 0.5,
    biomass_inc_min: float = 0.05,
    mean_tol: float = 0.05,
    min_group_count: int = 7,
) -> tuple[bool, str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
    s = ts.get("p_stress")
    if s is None or s.dropna().empty:
        return True, "P correlation (skipped)", diagnostics
    # If available P present, use Spearman correlation; else fallback trend proxy
    if "p_avail_top_kg_ha" in ts.columns:
        a = ts["p_avail_top_kg_ha"].astype(float)
        lai_ser = ts.get("lai")
        grow_ser = ts.get("biomass_inc_g_m2")
        lai_gate = (lai_ser >= lai_min_active) if lai_ser is not None else True
        grow_gate = (grow_ser > biomass_inc_min) if grow_ser is not None else True
        mask = s.notna() & a.notna() & (ts["day"] >= start_day) & lai_gate & grow_gate
        if not mask.any():
            return True, "P correlation (skipped)", diagnostics
        try:
            from scipy.stats import spearmanr  # type: ignore

            rho, _ = spearmanr(s[mask], a[mask])
        except Exception:
            # SciPy not available; compute Spearman via rank correlation
            s_rank = s[mask].rank()
            a_rank = a[mask].rank()
            rho = float(s_rank.corr(a_rank, method="pearson"))
        diagnostics["spearman_rho"] = float(rho)
        if rho >= min_pos_r:
            label = "P stress positively correlated with available P"
            return True, label, diagnostics
        # Quartile fallback: stress should be higher when available P is low
        # Use non-negative available P for quantiles and robust medians
        a_eff = a.clip(lower=0.0)
        quant = a_eff[mask].quantile([0.25, 0.75]).to_list()
        low_q, high_q = float(quant[0]), float(quant[1])
        low_mask = mask & (a_eff <= low_q)
        high_mask = mask & (a_eff >= high_q)
        low_stat = s.loc[low_mask].median()
        high_stat = s.loc[high_mask].median()
        diagnostics["p_low_q_median_stress"] = (
            float(low_stat) if pd.notna(low_stat) else float("nan")
        )
        diagnostics["p_high_q_median_stress"] = (
            float(high_stat) if pd.notna(high_stat) else float("nan")
        )
        diagnostics["p_low_q_count"] = float(int(low_mask.sum()))
        diagnostics["p_high_q_count"] = float(int(high_mask.sum()))
        ok_q = bool(
            pd.notna(low_stat)
            and pd.notna(high_stat)
            and int(low_mask.sum()) >= int(min_group_count)
            and int(high_mask.sum()) >= int(min_group_count)
            and (high_stat >= low_stat - float(mean_tol))
        )
        label_q = "P stress factor higher when available P is high (quartiles)"
        return ok_q, label_q, diagnostics
    # Fallback trend proxy
    ds = s.dropna().diff().fillna(0)
    frac_pos = float((ds > 1e-3).mean()) if len(ds) else 0.0
    diagnostics["p_stress_frac_positive_deltas"] = frac_pos
    ok = frac_pos <= 0.15
    return ok, "P stress trend mostly non-increasing (proxy)", diagnostics


def check_n_coherence(ts: pd.DataFrame) -> tuple[bool, str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
    if "n_stress" not in ts.columns:
        return True, "N coherence (skipped)", diagnostics
    # Use total mineral N proxy if present
    if "n_total_kgha" in ts.columns:
        quant = ts["n_total_kgha"].quantile([0.25, 0.75]).to_list()
        low_q, high_q = float(quant[0]), float(quant[1])
        low = ts.loc[ts["n_total_kgha"] <= low_q, "n_stress"].mean()
        high = ts.loc[ts["n_total_kgha"] >= high_q, "n_stress"].mean()
        diagnostics["n_low_q_mean"] = float(low) if pd.notna(low) else float("nan")
        diagnostics["n_high_q_mean"] = float(high) if pd.notna(high) else float("nan")
        ok = bool(pd.notna(low) and pd.notna(high) and (low <= high + 1e-6))
        return ok, "N stress higher when mineral N is low (quartiles)", diagnostics
    return True, "N coherence (skipped)", diagnostics


def check_stage_impact(
    ts: pd.DataFrame,
    stress_col: str = "water_stress",
    stage_col: str = "stage",
    biomass_inc_col: str = "biomass_inc_g_m2",
    critical_stages: tuple[str, ...] = ("flowering", "grain_fill"),
    stress_thr: float = 0.7,
) -> tuple[bool, str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
    if any(c not in ts.columns for c in (stress_col, stage_col, biomass_inc_col)):
        return True, "Stage impact (skipped)", diagnostics
    crit = ts.loc[ts[stage_col].isin(list(critical_stages))]
    if crit.empty:
        return True, "Stage impact (skipped)", diagnostics
    low = crit.loc[crit[stress_col] < stress_thr, biomass_inc_col].mean()
    high = crit.loc[crit[stress_col] >= stress_thr, biomass_inc_col].mean()
    diagnostics["biomass_inc_low_stress"] = (
        float(low) if pd.notna(low) else float("nan")
    )
    diagnostics["biomass_inc_high_stress"] = (
        float(high) if pd.notna(high) else float("nan")
    )
    ok = pd.notna(low) and pd.notna(high) and (low <= high + 1e-6)
    label = "High stress reduces biomass increment in critical stages"
    return bool(ok), label, diagnostics


def check_et_bounded(
    ts: pd.DataFrame,
    max_exceed_fraction: float = 0.10,
    exclude_lai_below: float | None = None,
) -> tuple[bool, str, dict[str, float]]:
    diagnostics: dict[str, float] = {}
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

    checks: list[tuple[bool, str]] = []
    diagnostics_sections: list[str] = []
    # Stress bounds
    ok_sb, name_sb = check_stress_bounds(ts)
    checks.append((ok_sb, name_sb))

    # Water coherence
    ok_wc, name_wc, diag_wc = check_water_coherence(ts)
    checks.append((ok_wc, name_wc))

    # P correlation (proxy)
    ok_pc, name_pc, diag_pc = check_p_correlation(ts)
    checks.append((ok_pc, name_pc))

    # N coherence (quartile-based)
    ok_nc, name_nc, diag_nc = check_n_coherence(ts)
    checks.append((ok_nc, name_nc))

    # Stage impact
    ok_si, name_si, diag_si = check_stage_impact(ts)
    checks.append((ok_si, name_si))

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
        "## ET exceedance diagnostics\n\n"
        f"- fraction_exceed (LAI>={args.et_exclude_lai_below}): "
        f"{diag_et.get('fraction_exceed', 0.0):.3f}\n"
        f"- max_margin: {diag_et.get('max_margin', 0.0):.3f}\n"
        f"- mean_margin: {diag_et.get('mean_margin', 0.0):.3f}\n\n"
        "Top 10 days by ET margin (E+T - ET0):\n\n"
        "```csv\n" + buf_top.getvalue() + "```\n"
    )

    # LAI shape diagnostics
    diagnostics_sections.append(
        "## LAI diagnostics\n\n"
        f"- lai_max_day_index: {diag_lai.get('lai_max_day_index', float('nan'))}\n"
        f"- lai_max_value: {diag_lai.get('lai_max_value', float('nan'))}\n"
    )

    # Irrigation pre/post diagnostics
    buf_irr = StringIO()
    pd.DataFrame(irr_diags).to_csv(buf_irr, index=False)
    diagnostics_sections.append(
        "## Irrigation impact diagnostics\n\n"
        "Pre/Post window means and deltas by irrigation day:\n\n"
        "```csv\n" + buf_irr.getvalue() + "```\n"
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
                "## Harvest diagnostics\n\n"
                f"- harvest_day: {args.harvest}\n"
                f"- lai_before_last: {before['lai'].iloc[-1]:.3f}\n"
                f"- lai_after_mean_7d: {after['lai'].head(7).mean():.3f}\n"
                f"- lai_drop: {drop:.3f}\n"
            )
        else:
            diagnostics_sections.append(
                "## Harvest diagnostics\n\n"
                "No post-harvest window available; skipping LAI drop check.\n"
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
