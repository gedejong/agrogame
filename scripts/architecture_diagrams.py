#!/usr/bin/env python3
"""Generate architecture diagrams for the AgroGame simulation engine.

Produces multi-faceted visualizations showing module structure, event flow,
state complexity, and test coverage.

Usage:
    poetry run python scripts/architecture_diagrams.py [--outdir DIR]
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.patches as mpatches  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
import numpy as np  # noqa: E402


OUTDIR = Path("out/architecture")

# ── Data ──────────────────────────────────────────────────────────────────

MODULES = {
    "Simulation\nEngine": {"lines": 1469, "files": 8, "tests": 22, "color": "#4c78a8"},
    "Weather\nGenerator": {"lines": 900, "files": 10, "tests": 60, "color": "#f58518"},
    "Soil Water": {"lines": 625, "files": 10, "tests": 30, "color": "#54a24b"},
    "Nitrogen\nCycle": {"lines": 600, "files": 8, "tests": 50, "color": "#e45756"},
    "Canopy\nModel": {"lines": 594, "files": 8, "tests": 37, "color": "#72b7b2"},
    "Microbial\nBiomass": {"lines": 532, "files": 5, "tests": 7, "color": "#b279a2"},
    "Phosphorus\nCycle": {"lines": 522, "files": 7, "tests": 7, "color": "#ff9da6"},
    "ET\nModule": {"lines": 501, "files": 6, "tests": 15, "color": "#9d755d"},
    "Plant\nRoots": {"lines": 377, "files": 7, "tests": 36, "color": "#bab0ac"},
    "Phenology": {"lines": 260, "files": 5, "tests": 10, "color": "#eeca3b"},
    "Plant\nBiomass": {"lines": 177, "files": 5, "tests": 14, "color": "#d67195"},
    "Soil\nChemistry": {"lines": 133, "files": 3, "tests": 1, "color": "#b07aa1"},
}

EVENTS_BY_CATEGORY = {
    "System": ["DayTick"],
    "Plant/Growth": [
        "GddAccumulated",
        "StageChanged",
        "RootDepthChanged",
        "RootDistribUpdated",
        "WaterStressComputed",
        "NutrientStressComputed",
        "BiomassPartitioned",
        "Harvested",
    ],
    "Water": [
        "WaterInfiltrated",
        "WaterDrained",
        "RunoffGenerated",
        "EvaporationTaken",
        "TranspByLayer",
        "CanopyIntercepted",
        "CanopyEvaporated",
    ],
    "Nutrients": [
        "NitrificationOcc",
        "MineralizationOcc",
        "DenitrificationOcc",
        "NutrientLeached",
        "PFixationOccurred",
        "SoilPHUpdated",
    ],
    "Microbes": [
        "MicrobialGrowth",
        "MicrobialMortality",
        "EnzymeProduced",
        "MicrobialSnapshot",
        "ActivityComputed",
        "SubstrateAvail",
        "PrimingPulse",
    ],
    "Canopy": [
        "LightIntercepted",
        "BiomassAccumulated",
        "LAIUpdated",
    ],
}

DAYTICK_PHASES = [
    ("day_start", "Initialize", "#f0f0f0"),
    ("chemistry", "Soil Chemistry", "#b07aa1"),
    ("water", "Water Balance", "#54a24b"),
    ("plant_structure", "Roots + Phenology", "#eeca3b"),
    ("et", "Evapotranspiration", "#9d755d"),
    ("nutrients", "N + P + Microbes", "#e45756"),
    ("canopy", "Canopy Growth", "#72b7b2"),
    ("day_end", "Diagnostics", "#f0f0f0"),
]

STATE_OBJECTS = {
    "SoilWaterState": {"fields": ["theta[]"], "per_layer": True},
    "SoilNitrogenState": {
        "fields": ["nh4[]", "no3[]", "organic_n[]"],
        "per_layer": True,
    },
    "SoilPhosphorusState": {
        "fields": ["available_p[]", "fixed_p[]", "organic_p[]"],
        "per_layer": True,
    },
    "PhenologyState": {
        "fields": ["accumulated_gdd", "stage", "vernal_units"],
        "per_layer": False,
    },
    "CanopyState": {
        "fields": ["lai", "biomass", "stem_biomass", "grain_biomass"],
        "per_layer": False,
    },
    "RootState": {
        "fields": ["depth_cm", "biomass", "layer_fracs[]"],
        "per_layer": False,
    },
    "MicrobialState": {
        "fields": ["c_kg_ha[]", "n_kg_ha[]", "fungal_frac[]"],
        "per_layer": True,
    },
    "EtState": {"fields": ["cumul_evap_mm"], "per_layer": False},
}

CROPS = [
    "Maize",
    "Winter\nWheat",
    "Spring\nWheat",
    "Rice",
    "Sorghum",
    "Soybean",
    "Grape",
]
CLIMATES = ["Netherlands\nTemperate", "Kenya\nHighlands", "Sahel\nArid"]


def fig1_module_landscape(outdir: Path) -> None:
    """Bubble chart: module size (area) vs test density (color), labeled."""
    fig, ax = plt.subplots(figsize=(14, 9))

    names = list(MODULES.keys())
    lines = [MODULES[n]["lines"] for n in names]
    tests = [MODULES[n]["tests"] for n in names]
    test_density = [
        t / max(loc, 1) * 1000 for t, loc in zip(tests, lines, strict=False)
    ]

    # Bubble size proportional to LOC
    sizes = [loc * 0.8 for loc in lines]

    scatter = ax.scatter(
        range(len(names)),
        lines,
        s=sizes,
        c=test_density,
        cmap="RdYlGn",
        alpha=0.85,
        edgecolors="white",
        linewidth=2,
        vmin=0,
        vmax=100,
        zorder=3,
    )

    for i, name in enumerate(names):
        ax.annotate(
            name,
            (i, lines[i]),
            ha="center",
            va="center",
            fontsize=7,
            fontweight="bold",
            color="black",
            zorder=4,
        )
        ax.annotate(
            f"{tests[i]} tests",
            (i, lines[i] - 80),
            ha="center",
            va="top",
            fontsize=6,
            color="#555",
            zorder=4,
        )

    cbar = plt.colorbar(scatter, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("Test density (tests per 1000 LOC)", fontsize=9)

    ax.set_xticks([])
    ax.set_ylabel("Lines of Code", fontsize=11)
    ax.set_title(
        "AgroGame Module Landscape\n"
        "Bubble size = LOC | Color = test density (green = well-tested)",
        fontsize=13,
        fontweight="bold",
    )
    ax.set_xlim(-0.8, len(names) - 0.2)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    ax.set_axisbelow(True)

    fig.tight_layout()
    fig.savefig(str(outdir / "01_module_landscape.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 01_module_landscape.png")


def fig2_event_sunburst(outdir: Path) -> None:
    """Nested pie chart showing event categories and counts."""
    fig, ax = plt.subplots(figsize=(10, 10))

    categories = list(EVENTS_BY_CATEGORY.keys())
    counts = [len(EVENTS_BY_CATEGORY[c]) for c in categories]
    total = sum(counts)

    cat_colors = ["#4c78a8", "#eeca3b", "#54a24b", "#e45756", "#b279a2", "#72b7b2"]

    # Outer ring: individual events
    outer_labels = []
    outer_colors = []
    for i, cat in enumerate(categories):
        for ev in EVENTS_BY_CATEGORY[cat]:
            outer_labels.append(ev)
            outer_colors.append(cat_colors[i])

    outer_sizes = [1] * len(outer_labels)

    # Inner ring: categories
    wedges1, _ = ax.pie(
        counts,
        radius=0.7,
        colors=cat_colors,
        wedgeprops={"width": 0.3, "edgecolor": "white", "linewidth": 2},
        startangle=90,
    )

    wedges2, texts2 = ax.pie(
        outer_sizes,
        radius=1.0,
        colors=outer_colors,
        wedgeprops={"width": 0.3, "edgecolor": "white", "linewidth": 1},
        startangle=90,
        labels=outer_labels,
        labeldistance=1.15,
        textprops={"fontsize": 6},
    )

    # Category labels on inner ring
    for i, (wedge, cat) in enumerate(zip(wedges1, categories, strict=False)):
        ang = (wedge.theta2 + wedge.theta1) / 2
        x = 0.55 * math.cos(math.radians(ang))
        y = 0.55 * math.sin(math.radians(ang))
        ax.text(
            x,
            y,
            f"{cat}\n({counts[i]})",
            ha="center",
            va="center",
            fontsize=8,
            fontweight="bold",
        )

    ax.set_title(
        f"Event Bus Architecture — {total} Event Types\n"
        "Inner ring: categories | Outer ring: individual events",
        fontsize=13,
        fontweight="bold",
        pad=20,
    )

    fig.tight_layout()
    fig.savefig(str(outdir / "02_event_sunburst.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 02_event_sunburst.png")


def fig3_daily_pipeline(outdir: Path) -> None:
    """Horizontal pipeline showing DayTick phase execution order."""
    fig, ax = plt.subplots(figsize=(16, 5))

    n = len(DAYTICK_PHASES)
    box_w = 1.6
    box_h = 1.2
    gap = 0.4
    y_center = 2.5

    for i, (phase, label, color) in enumerate(DAYTICK_PHASES):
        x = i * (box_w + gap)
        box = FancyBboxPatch(
            (x, y_center - box_h / 2),
            box_w,
            box_h,
            boxstyle="round,pad=0.15",
            facecolor=color,
            edgecolor="#333",
            linewidth=1.5,
            alpha=0.9,
        )
        ax.add_patch(box)
        ax.text(
            x + box_w / 2,
            y_center + 0.15,
            label,
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
        )
        ax.text(
            x + box_w / 2,
            y_center - 0.25,
            phase,
            ha="center",
            va="center",
            fontsize=7,
            color="#555",
            style="italic",
        )

        if i < n - 1:
            ax.annotate(
                "",
                xy=(x + box_w + gap - 0.05, y_center),
                xytext=(x + box_w + 0.05, y_center),
                arrowprops={"arrowstyle": "->", "color": "#333", "lw": 2},
            )

    ax.set_xlim(-0.3, n * (box_w + gap))
    ax.set_ylim(0.5, 4.5)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(
        "Daily Simulation Pipeline — 8 Phased DayTick Events\n"
        "Each phase triggers subscribed modules via EventBus",
        fontsize=13,
        fontweight="bold",
    )

    fig.tight_layout()
    fig.savefig(str(outdir / "03_daily_pipeline.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 03_daily_pipeline.png")


def fig4_state_complexity(outdir: Path) -> None:
    """Horizontal bar chart of state object field counts, colored by per-layer."""
    fig, ax = plt.subplots(figsize=(10, 6))

    names = list(STATE_OBJECTS.keys())
    field_counts = [len(STATE_OBJECTS[n]["fields"]) for n in names]
    is_per_layer = [STATE_OBJECTS[n]["per_layer"] for n in names]
    colors = ["#e45756" if pl else "#4c78a8" for pl in is_per_layer]

    y_pos = range(len(names))
    bars = ax.barh(y_pos, field_counts, color=colors, edgecolor="white", height=0.7)

    for i, (bar, name) in enumerate(zip(bars, names, strict=False)):
        fields = STATE_OBJECTS[name]["fields"]
        field_str = ", ".join(fields)
        ax.text(
            bar.get_width() + 0.1,
            i,
            field_str,
            va="center",
            fontsize=7,
            color="#555",
        )

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=9)
    ax.set_xlabel("Number of State Fields", fontsize=11)
    ax.set_title(
        "Simulation State Complexity\n"
        "Red = per-layer (multiplied by soil depth) | Blue = scalar",
        fontsize=13,
        fontweight="bold",
    )
    ax.invert_yaxis()
    ax.set_xlim(0, max(field_counts) + 3)

    legend_elements = [
        mpatches.Patch(facecolor="#e45756", label="Per-layer state (× n_layers)"),
        mpatches.Patch(facecolor="#4c78a8", label="Scalar state"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", fontsize=9)

    fig.tight_layout()
    fig.savefig(str(outdir / "04_state_complexity.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 04_state_complexity.png")


def fig5_scenario_matrix(outdir: Path) -> None:
    """Heatmap of 7 crops x 3 climates realism test coverage."""
    crop_labels = CROPS
    climate_labels = CLIMATES

    # Coverage matrix: 1=tested, 0.5=partial, 0=untested
    # Based on test_realism.py scenarios
    matrix = np.array(
        [
            # NL     Kenya  Sahel
            [1.0, 1.0, 1.0],  # Maize
            [1.0, 1.0, 1.0],  # Winter Wheat
            [1.0, 1.0, 0.0],  # Spring Wheat
            [0.0, 1.0, 1.0],  # Rice
            [1.0, 0.0, 1.0],  # Sorghum
            [0.0, 0.0, 0.0],  # Soybean
            [1.0, 0.0, 1.0],  # Grape
        ]
    )

    fig, ax = plt.subplots(figsize=(8, 7))
    cmap = plt.cm.RdYlGn
    im = ax.imshow(matrix, cmap=cmap, aspect="auto", vmin=0, vmax=1)

    ax.set_xticks(range(len(climate_labels)))
    ax.set_xticklabels(climate_labels, fontsize=10)
    ax.set_yticks(range(len(crop_labels)))
    ax.set_yticklabels(crop_labels, fontsize=10)

    for i in range(len(crop_labels)):
        for j in range(len(climate_labels)):
            val = matrix[i, j]
            label = "Tested" if val == 1.0 else "Partial" if val == 0.5 else "—"
            color = "white" if val < 0.5 else "black"
            ax.text(j, i, label, ha="center", va="center", fontsize=9, color=color)

    ax.set_title(
        "Crop x Climate Realism Test Matrix\n"
        "7 crops x 3 climates = 21 possible scenarios",
        fontsize=13,
        fontweight="bold",
    )

    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_ticks([0, 0.5, 1])
    cbar.set_ticklabels(["Untested", "Partial", "Tested"])

    fig.tight_layout()
    fig.savefig(str(outdir / "05_scenario_matrix.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 05_scenario_matrix.png")


def fig6_system_overview(outdir: Path) -> None:
    """Multi-panel overview combining key metrics."""
    fig = plt.figure(figsize=(18, 12))
    fig.suptitle(
        "AgroGame Simulation Engine — System Overview",
        fontsize=16,
        fontweight="bold",
        y=0.98,
    )

    # Panel 1: LOC by subsystem (treemap-like bar)
    ax1 = fig.add_subplot(2, 3, 1)
    names = list(MODULES.keys())
    lines = [MODULES[n]["lines"] for n in names]
    colors = [MODULES[n]["color"] for n in names]
    idx = np.argsort(lines)[::-1]
    sorted_names = [names[i] for i in idx]
    sorted_lines = [lines[i] for i in idx]
    sorted_colors = [colors[i] for i in idx]
    ax1.barh(
        range(len(sorted_names)), sorted_lines, color=sorted_colors, edgecolor="white"
    )
    ax1.set_yticks(range(len(sorted_names)))
    ax1.set_yticklabels(sorted_names, fontsize=7)
    ax1.invert_yaxis()
    ax1.set_xlabel("Lines of Code")
    ax1.set_title("Module Size", fontweight="bold", fontsize=11)

    # Panel 2: Event counts by category
    ax2 = fig.add_subplot(2, 3, 2)
    cats = list(EVENTS_BY_CATEGORY.keys())
    ecounts = [len(EVENTS_BY_CATEGORY[c]) for c in cats]
    cat_colors = ["#4c78a8", "#eeca3b", "#54a24b", "#e45756", "#b279a2", "#72b7b2"]
    ax2.bar(range(len(cats)), ecounts, color=cat_colors, edgecolor="white")
    ax2.set_xticks(range(len(cats)))
    ax2.set_xticklabels(cats, fontsize=8, rotation=30, ha="right")
    ax2.set_ylabel("Event Types")
    ax2.set_title(f"Event Bus — {sum(ecounts)} Types", fontweight="bold", fontsize=11)

    # Panel 3: Key numbers
    ax3 = fig.add_subplot(2, 3, 3)
    ax3.axis("off")
    stats = [
        ("11,752", "Lines of Python"),
        ("12", "Simulation Modules"),
        ("34", "Event Types"),
        ("8", "Daily Phases"),
        ("8", "State Objects"),
        ("7", "Crop Presets"),
        ("3", "Climate Zones"),
        ("414+", "Test Functions"),
        ("92%+", "Code Coverage"),
    ]
    for i, (num, label) in enumerate(stats):
        row = i // 3
        col = i % 3
        x = 0.17 + col * 0.33
        y = 0.85 - row * 0.35
        ax3.text(
            x,
            y,
            num,
            ha="center",
            va="center",
            fontsize=20,
            fontweight="bold",
            color="#4c78a8",
        )
        ax3.text(x, y - 0.12, label, ha="center", va="center", fontsize=8, color="#555")
    ax3.set_title("Key Metrics", fontweight="bold", fontsize=11)

    # Panel 4: Test density per module
    ax4 = fig.add_subplot(2, 3, 4)
    test_density = [
        MODULES[n]["tests"] / max(MODULES[n]["lines"], 1) * 1000 for n in names
    ]
    idx_td = np.argsort(test_density)[::-1]
    td_names = [names[i] for i in idx_td]
    td_vals = [test_density[i] for i in idx_td]
    td_colors = [
        "#54a24b" if v > 50 else "#eeca3b" if v > 20 else "#e45756" for v in td_vals
    ]
    ax4.barh(range(len(td_names)), td_vals, color=td_colors, edgecolor="white")
    ax4.set_yticks(range(len(td_names)))
    ax4.set_yticklabels(td_names, fontsize=7)
    ax4.invert_yaxis()
    ax4.set_xlabel("Tests per 1000 LOC")
    ax4.set_title("Test Density", fontweight="bold", fontsize=11)
    ax4.axvline(50, color="#54a24b", ls="--", alpha=0.5, lw=1)

    # Panel 5: State fields (per-layer vs scalar)
    ax5 = fig.add_subplot(2, 3, 5)
    state_names = list(STATE_OBJECTS.keys())
    state_fields = [len(STATE_OBJECTS[s]["fields"]) for s in state_names]
    state_colors = [
        "#e45756" if STATE_OBJECTS[s]["per_layer"] else "#4c78a8" for s in state_names
    ]
    ax5.barh(
        range(len(state_names)), state_fields, color=state_colors, edgecolor="white"
    )
    ax5.set_yticks(range(len(state_names)))
    ax5.set_yticklabels(state_names, fontsize=7)
    ax5.invert_yaxis()
    ax5.set_xlabel("Fields")
    ax5.set_title("State Complexity", fontweight="bold", fontsize=11)

    # Panel 6: Daily pipeline (compact)
    ax6 = fig.add_subplot(2, 3, 6)
    ax6.axis("off")
    phases = DAYTICK_PHASES
    for i, (_phase, label, color) in enumerate(phases):
        y = 0.92 - i * 0.115
        rect = mpatches.FancyBboxPatch(
            (0.05, y - 0.04),
            0.9,
            0.08,
            boxstyle="round,pad=0.02",
            facecolor=color,
            edgecolor="#555",
        )
        ax6.add_patch(rect)
        ax6.text(
            0.5,
            y,
            f"{i+1}. {label}",
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
        )
        if i < len(phases) - 1:
            ax6.annotate(
                "",
                xy=(0.5, y - 0.045),
                xytext=(0.5, y - 0.065),
                arrowprops={"arrowstyle": "->", "color": "#333", "lw": 1.5},
            )
    ax6.set_title("Daily Pipeline", fontweight="bold", fontsize=11)
    ax6.set_xlim(0, 1)
    ax6.set_ylim(0, 1)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(str(outdir / "06_system_overview.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("  Saved 06_system_overview.png")


def main() -> None:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("Generating AgroGame architecture diagrams...")

    fig1_module_landscape(OUTDIR)
    fig2_event_sunburst(OUTDIR)
    fig3_daily_pipeline(OUTDIR)
    fig4_state_complexity(OUTDIR)
    fig5_scenario_matrix(OUTDIR)
    fig6_system_overview(OUTDIR)

    print(f"\nDone. All diagrams saved to {OUTDIR}/")


if __name__ == "__main__":
    main()
