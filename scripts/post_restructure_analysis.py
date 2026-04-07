"""Post-restructure validation: statistical analysis and diagnostic plots."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT = Path("out/validation")


def load_data() -> pd.DataFrame:
    df = pd.read_csv("out/plots/full_integration_timeseries.csv")
    df["day"] = df["day"].astype(int)
    return df


def descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "lai",
        "biomass_g_m2",
        "evap_mm",
        "transp_mm",
        "et0_mm",
        "water_stress",
        "n_stress",
        "p_stress",
        "root_depth_cm",
    ]
    present = [c for c in cols if c in df.columns]
    desc = df[present].describe()
    desc.loc["range"] = desc.loc["max"] - desc.loc["min"]
    desc.loc["cv"] = desc.loc["std"] / desc.loc["mean"].replace(0, np.nan)
    return desc


def correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "lai",
        "biomass_g_m2",
        "evap_mm",
        "transp_mm",
        "et0_mm",
        "water_stress",
        "n_stress",
        "p_stress",
        "root_depth_cm",
    ]
    present = [c for c in cols if c in df.columns]
    return df[present].corr()


def plot_timeseries_panel(df: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 3, figsize=(16, 12))
    fig.suptitle("Post-Restructure Validation — 120-day Simulation", fontsize=14)

    # 1. LAI
    ax = axes[0, 0]
    ax.plot(df["day"], df["lai"], color="green", linewidth=1.5)
    ax.set_title("Leaf Area Index")
    ax.set_ylabel("LAI (m²/m²)")
    ax.grid(alpha=0.3)

    # 2. Biomass
    ax = axes[0, 1]
    ax.plot(df["day"], df["biomass_g_m2"], color="darkorange", linewidth=1.5)
    ax.set_title("Above-ground Biomass")
    ax.set_ylabel("Biomass (g/m²)")
    ax.grid(alpha=0.3)

    # 3. Biomass increment
    ax = axes[0, 2]
    ax.bar(df["day"], df["biomass_inc_g_m2"], color="goldenrod", alpha=0.7, width=1)
    ax.set_title("Daily Biomass Increment")
    ax.set_ylabel("g/m²/day")
    ax.grid(alpha=0.3)

    # 4. ET components
    ax = axes[1, 0]
    ax.plot(df["day"], df["et0_mm"], label="ET0", linestyle="--", color="gray")
    ax.plot(df["day"], df["evap_mm"], label="Evaporation", color="skyblue")
    ax.plot(df["day"], df["transp_mm"], label="Transpiration", color="steelblue")
    if "pot_transp_mm" in df.columns:
        ax.plot(
            df["day"],
            df["pot_transp_mm"],
            label="Pot. Transp",
            linestyle=":",
            color="navy",
        )
    ax.set_title("Evapotranspiration Components")
    ax.set_ylabel("mm/day")
    ax.legend(fontsize=7, loc="upper left")
    ax.grid(alpha=0.3)

    # 5. Water stress
    ax = axes[1, 1]
    ax.plot(df["day"], df["water_stress"], color="dodgerblue", linewidth=1.5)
    ax.axhline(1.0, color="green", linestyle="--", alpha=0.4, label="No stress")
    ax.axhline(0.5, color="orange", linestyle="--", alpha=0.4, label="Moderate")
    ax.set_title("Water Stress Factor")
    ax.set_ylabel("Stress (0=max, 1=none)")
    ax.set_ylim(-0.05, 1.1)
    ax.legend(fontsize=7)
    ax.grid(alpha=0.3)

    # 6. N and P stress
    ax = axes[1, 2]
    ax.plot(df["day"], df["n_stress"], label="N stress", color="darkgreen")
    ax.plot(df["day"], df["p_stress"], label="P stress", color="purple")
    ax.set_title("Nutrient Stress Factors")
    ax.set_ylabel("Stress (0=max, 1=none)")
    ax.set_ylim(-0.05, 1.1)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    # 7. Root depth
    ax = axes[2, 0]
    ax.plot(df["day"], df["root_depth_cm"], color="saddlebrown", linewidth=1.5)
    ax.invert_yaxis()
    ax.set_title("Root Depth")
    ax.set_ylabel("Depth (cm)")
    ax.set_xlabel("Day")
    ax.grid(alpha=0.3)

    # 8. P availability
    ax = axes[2, 1]
    ax.plot(df["day"], df["p_avail_top_kg_ha"], color="purple", linewidth=1.5)
    ax.set_title("Available P (top layer)")
    ax.set_ylabel("kg P/ha")
    ax.set_xlabel("Day")
    ax.grid(alpha=0.3)

    # 9. Phenology stages as colored bands
    ax = axes[2, 2]
    stage_colors = {
        "PLANTED": "#d4edda",
        "EMERGED": "#c3e6cb",
        "VEGETATIVE": "#b1dbb5",
        "FLOWERING": "#ffeeba",
        "GRAIN_FILL": "#f5c6a5",
        "MATURITY": "#f8d7da",
    }
    prev_stage = None
    start = 0
    for _i, row in df.iterrows():
        s = row["stage"]
        if s != prev_stage and prev_stage is not None:
            color = stage_colors.get(prev_stage, "#eeeeee")
            ax.axvspan(start, row["day"], alpha=0.5, color=color, label=prev_stage)
            start = row["day"]
        prev_stage = s
    if prev_stage:
        color = stage_colors.get(prev_stage, "#eeeeee")
        ax.axvspan(start, df["day"].iloc[-1], alpha=0.5, color=color, label=prev_stage)
    # Remove duplicate labels
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles, strict=False))
    ax.legend(by_label.values(), by_label.keys(), fontsize=7, loc="center")
    ax.set_title("Phenology Timeline")
    ax.set_xlabel("Day")
    ax.set_yticks([])

    plt.tight_layout()
    fig.savefig(OUT / "timeseries_panel.png", dpi=150)
    plt.close()


def plot_correlation_heatmap(corr: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(corr.columns)))
    ax.set_xticklabels(corr.columns, rotation=45, ha="right", fontsize=9)
    ax.set_yticks(range(len(corr.index)))
    ax.set_yticklabels(corr.index, fontsize=9)
    for i in range(len(corr.index)):
        for j in range(len(corr.columns)):
            v = corr.values[i, j]
            color = "white" if abs(v) > 0.6 else "black"
            ax.text(j, i, f"{v:.2f}", va="center", ha="center", color=color, fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    ax.set_title("Variable Correlation Matrix (120-day simulation)")
    fig.tight_layout()
    fig.savefig(OUT / "correlation_heatmap.png", dpi=150)
    plt.close()


def plot_phase_boxplots(df: pd.DataFrame) -> None:
    """Box plots of key variables grouped by phenology stage."""
    stage_order = [
        s
        for s in [
            "PLANTED",
            "EMERGED",
            "VEGETATIVE",
            "FLOWERING",
            "GRAIN_FILL",
            "MATURITY",
        ]
        if s in df["stage"].values
    ]
    if not stage_order:
        return
    variables = ["evap_mm", "transp_mm", "water_stress", "biomass_inc_g_m2"]
    present = [v for v in variables if v in df.columns]
    fig, axes = plt.subplots(1, len(present), figsize=(4 * len(present), 5))
    if len(present) == 1:
        axes = [axes]
    for ax, var in zip(axes, present, strict=False):
        data = [df[df["stage"] == s][var].dropna().values for s in stage_order]
        bp = ax.boxplot(data, tick_labels=stage_order, patch_artist=True)
        colors = ["#d4edda", "#c3e6cb", "#b1dbb5", "#ffeeba", "#f5c6a5", "#f8d7da"]
        for patch, color in zip(bp["boxes"], colors[: len(stage_order)], strict=False):
            patch.set_facecolor(color)
        ax.set_title(var.replace("_", " ").title(), fontsize=10)
        ax.tick_params(axis="x", rotation=45)
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle("Variable Distributions by Phenology Stage", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "phase_boxplots.png", dpi=150)
    plt.close()


def plot_scatter_matrix(df: pd.DataFrame) -> None:
    """Scatter plots of key biophysical relationships."""
    fig, axes = plt.subplots(2, 2, figsize=(10, 9))

    # LAI vs Transpiration
    ax = axes[0, 0]
    ax.scatter(df["lai"], df["transp_mm"], s=10, alpha=0.6, c=df["day"], cmap="viridis")
    ax.set_xlabel("LAI (m²/m²)")
    ax.set_ylabel("Transpiration (mm/day)")
    ax.set_title("LAI vs Transpiration")
    ax.grid(alpha=0.3)

    # Biomass vs Root depth
    ax = axes[0, 1]
    ax.scatter(
        df["biomass_g_m2"],
        df["root_depth_cm"],
        s=10,
        alpha=0.6,
        c=df["day"],
        cmap="viridis",
    )
    ax.set_xlabel("Biomass (g/m²)")
    ax.set_ylabel("Root depth (cm)")
    ax.set_title("Biomass vs Root Depth")
    ax.grid(alpha=0.3)

    # Water stress vs Transpiration ratio
    ax = axes[1, 0]
    ratio = df["transp_mm"] / df["pot_transp_mm"].replace(0, np.nan)
    ax.scatter(df["water_stress"], ratio, s=10, alpha=0.6, c=df["day"], cmap="viridis")
    ax.set_xlabel("Water Stress Factor")
    ax.set_ylabel("Actual / Potential Transpiration")
    ax.set_title("Water Stress vs Transpiration Ratio")
    ax.grid(alpha=0.3)

    # ET0 vs Evaporation
    ax = axes[1, 1]
    sc = ax.scatter(
        df["et0_mm"], df["evap_mm"], s=10, alpha=0.6, c=df["day"], cmap="viridis"
    )
    ax.set_xlabel("ET0 (mm/day)")
    ax.set_ylabel("Evaporation (mm/day)")
    ax.set_title("ET0 vs Actual Evaporation")
    ax.grid(alpha=0.3)
    fig.colorbar(sc, ax=axes.ravel().tolist(), label="Day", shrink=0.6)

    fig.suptitle("Biophysical Relationships (color = day)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "scatter_relationships.png", dpi=150)
    plt.close()


def sanity_checks(df: pd.DataFrame) -> list[str]:
    """Run physical sanity checks on simulation output."""
    results = []

    # 1. Biomass should be monotonically non-decreasing (no negative growth)
    neg_growth = (df["biomass_inc_g_m2"] < -0.01).sum()
    mono_status = (
        "PASS" if neg_growth == 0 else f"WARN — {neg_growth} days with negative growth"
    )
    results.append(f"Biomass monotonicity: {mono_status}")

    # 2. Water stress should be in [0, 1]
    ws = df["water_stress"]
    ws_ok = (ws >= -0.01).all() and (ws <= 1.01).all()
    results.append(f"Water stress bounds [0,1]: {'PASS' if ws_ok else 'FAIL'}")

    # 3. ET0 should be positive
    et0_ok = (df["et0_mm"] >= 0).all()
    results.append(f"ET0 non-negative: {'PASS' if et0_ok else 'FAIL'}")

    # 4. Transpiration <= potential transpiration
    excess = (df["transp_mm"] > df["pot_transp_mm"] + 0.01).sum()
    transp_status = "PASS" if excess == 0 else f"FAIL — {excess} violations"
    results.append(f"Transpiration <= potential: {transp_status}")

    # 5. Root depth should increase over time (generally)
    rd = df["root_depth_cm"]
    rd_increasing = rd.iloc[-1] >= rd.iloc[0]
    results.append(f"Root depth increases: {'PASS' if rd_increasing else 'WARN'}")

    # 6. LAI should reach > 0 at some point
    lai_active = (df["lai"] > 0.01).any()
    results.append(
        f"LAI becomes active: {'PASS' if lai_active else 'WARN — LAI stayed near zero'}"
    )

    # 7. Phenology progresses through stages
    stages = df["stage"].unique()
    results.append(f"Phenology stages observed: {', '.join(stages)}")
    multi_stage = len(stages) > 1
    results.append(
        f"Stage progression: {'PASS' if multi_stage else 'WARN — single stage'}"
    )

    # 8. Water balance: evap + transp should not exceed ET0 consistently
    et_ratio = (df["evap_mm"] + df["transp_mm"]) / df["et0_mm"].replace(0, np.nan)
    excess_et = (et_ratio > 1.5).sum()
    et_status = "PASS" if excess_et == 0 else f"WARN — {excess_et} days exceed 150%"
    results.append(f"ET balance (actual/ET0 < 1.5): {et_status}")

    # 9. N and P stress in bounds
    for name in ["n_stress", "p_stress"]:
        s = df[name]
        ok = (s >= -0.01).all() and (s <= 1.01).all()
        results.append(f"{name} bounds [0,1]: {'PASS' if ok else 'FAIL'}")

    # 10. P availability should decline (uptake > inputs in this scenario)
    p_decline = df["p_avail_top_kg_ha"].iloc[-1] < df["p_avail_top_kg_ha"].iloc[0]
    results.append(
        f"P depletion trend: {'PASS' if p_decline else 'INFO — P stable or increasing'}"
    )

    return results


def write_report(
    df: pd.DataFrame,
    desc: pd.DataFrame,
    corr: pd.DataFrame,
    checks: list[str],
) -> None:
    report = OUT / "validation_report.md"
    with report.open("w") as f:
        f.write("# Post-Restructure Validation Report\n\n")
        f.write("**Simulation**: 120 days, loam_temperate, cycled 3-day weather\n\n")

        f.write("## Sanity Checks\n\n")
        for c in checks:
            status = "PASS" if "PASS" in c else ("FAIL" if "FAIL" in c else "INFO")
            icon = {"PASS": "+", "FAIL": "!", "INFO": "~", "WARN": "~"}.get(
                c.split(":")[0].split()[-1] if ":" in c else status, "~"
            )
            f.write(f"- [{icon}] {c}\n")

        f.write("\n## Descriptive Statistics\n\n")
        f.write(desc.round(4).to_string())

        f.write("\n\n## Correlation Matrix\n\n")
        f.write(corr.round(3).to_string())

        f.write("\n\n## Growth Phase Statistics\n\n")
        stage_order = [
            s
            for s in [
                "PLANTED",
                "EMERGED",
                "VEGETATIVE",
                "FLOWERING",
                "GRAIN_FILL",
                "MATURITY",
            ]
            if s in df["stage"].values
        ]
        for stage in stage_order:
            sub = df[df["stage"] == stage]
            day_min = sub["day"].min()
            day_max = sub["day"].max()
            f.write(f"\n### {stage} (days {day_min}" f"–{day_max}, n={len(sub)})\n\n")
            key = ["lai", "biomass_g_m2", "evap_mm", "transp_mm", "water_stress"]
            present = [k for k in key if k in sub.columns]
            f.write(sub[present].describe().round(4).to_string())
            f.write("\n")

        f.write("\n## Figures\n\n")
        f.write("### Time Series Panel\n![](timeseries_panel.png)\n\n")
        f.write("### Correlation Heatmap\n![](correlation_heatmap.png)\n\n")
        f.write("### Distributions by Phase\n![](phase_boxplots.png)\n\n")
        f.write("### Biophysical Scatter Plots\n![](scatter_relationships.png)\n\n")

    print(f"Report written to {report}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_data()

    desc = descriptive_stats(df)
    corr = correlation_matrix(df)
    checks = sanity_checks(df)

    plot_timeseries_panel(df)
    plot_correlation_heatmap(corr)
    plot_phase_boxplots(df)
    plot_scatter_matrix(df)
    write_report(df, desc, corr, checks)

    print("\n=== SANITY CHECKS ===")
    for c in checks:
        print(f"  {c}")
    print("\n=== DESCRIPTIVE STATISTICS ===")
    print(desc.round(4).to_string())
    print("\n=== CORRELATION MATRIX (selected) ===")
    print(corr.round(3).to_string())


if __name__ == "__main__":
    main()
