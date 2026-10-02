#!/usr/bin/env python
"""Per-hectare gross-margin harness for the economy (#508 Phase A, #438 Phase B).

Drives real API sessions through the same ``/step`` + ``/action`` code path the
Godot client uses, over the curated scenario catalog
(``game/scripts/scenario_catalog.gd``) and a fixed representative management
plan, and prints the #438 margin table: maturity, grain, revenue, every ledger
cost category, and the resulting margin.

This is the measurement that found the #508 bugs — costs were read off the live
ledger, not off ``prices.yaml``, where every line looked plausible. Re-run it on
both sides of any economy or yield change and paste both tables:

    poetry run python scripts/economy_margins.py

Seeds 42-46 are averaged so a single lucky weather draw cannot move a verdict.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from typing import Any

# Curated start-of-game scenarios, mirroring game/scripts/scenario_catalog.gd.
# Each entry is (soil_profile_key, crop_key, climate_key, area_fraction).
SCENARIOS: dict[str, list[tuple[str, str, str, float]]] = {
    "nl_maize_3soil": [
        ("sandy_temperate", "maize", "netherlands_temperate", 0.333),
        ("loam_temperate", "maize", "netherlands_temperate", 0.334),
        ("clay_temperate", "maize", "netherlands_temperate", 0.333),
    ],
    "kenya_maize": [("loam_temperate", "maize", "kenya_highlands", 1.0)],
    "sahel_sorghum": [("sandy_subsaharan", "sorghum", "sahel_arid", 1.0)],
    "kenya_rice_clay": [("clay_temperate", "rice", "kenya_highlands", 1.0)],
    "nl_spring_wheat": [
        ("clay_netherlands", "spring_wheat", "netherlands_temperate", 1.0)
    ],
    "nl_winter_wheat": [
        ("clay_netherlands", "winter_wheat", "netherlands_temperate", 1.0)
    ],
}

#: Seeds averaged per scenario.
SEEDS: tuple[int, ...] = (42, 43, 44, 45, 46)

#: The #438 representative plan. Planting is *not* an action here: catalog games
#: start pre-planted, and seed is charged at season start (#508). Fertiliser
#: amounts are kg of **nutrient element** per ha, which is what the engine
#: applies and (post-#508) what the price table charges for.
PLAN: dict[int, list[tuple[str, dict[str, Any]]]] = {
    1: [("tillage", {})],
    10: [("fertilize", {"type": "ammonium_nitrate", "amount_kg_ha": 50.0})],
    45: [("fertilize", {"type": "ammonium_nitrate", "amount_kg_ha": 50.0})],
}

#: Extra irrigation applied only to maize scenarios (#438 representative plan).
IRRIGATION_PLAN: dict[int, list[tuple[str, dict[str, Any]]]] = {
    30: [("irrigate", {"amount_mm": 20.0})],
    60: [("irrigate", {"amount_mm": 20.0})],
}

#: Ledger cost categories reported, in column order.
CATEGORIES: tuple[str, ...] = ("seed", "fertilize", "irrigate", "tillage", "harvest")

#: Hard cap on simulated days so a non-maturing crop cannot hang the harness.
MAX_DAYS = 400

#: Starting credits — large enough that no action is ever refused for funds,
#: so the table measures prices rather than affordability.
STARTING_CREDITS = 1_000_000


def _plan_for(crop_key: str) -> dict[int, list[tuple[str, dict[str, Any]]]]:
    """Representative plan for a crop: the base plan, plus irrigation for maize."""
    plan = {day: list(acts) for day, acts in PLAN.items()}
    if crop_key == "maize":
        for day, acts in IRRIGATION_PLAN.items():
            plan.setdefault(day, []).extend(acts)
    return plan


def run_scenario(client: Any, scenario: str, seed: int) -> dict[str, float]:
    """Run one scenario at one seed and return its per-hectare economics.

    Steps one day at a time (the client's own path), applies the representative
    plan on its scheduled days, harvests once the season completes, and reads
    the resulting costs straight off the ledger rather than recomputing them.
    """
    from agrogame.api.state import games

    patches = [
        {
            "soil_profile_key": soil,
            "crop_key": crop,
            "climate_key": climate,
            "area_fraction": frac,
        }
        for soil, crop, climate, frac in SCENARIOS[scenario]
    ]
    created = client.post(
        "/api/v1/games",
        json={
            "fields": [{"field_id": "field_1", "patches": patches}],
            "starting_credits": STARTING_CREDITS,
        },
    )
    if created.status_code != 200:
        raise RuntimeError(f"{scenario}/{seed}: create failed: {created.text}")
    game_id = created.json()["game_id"]
    session = games[game_id]
    crop_key = SCENARIOS[scenario][0][1]
    plan = _plan_for(crop_key)

    matured = False
    day = 0
    while day < MAX_DAYS:
        url = f"/api/v1/games/{game_id}/step?days=1"
        resp = client.post(url + (f"&seed={seed}" if day == 0 else ""))
        if resp.status_code != 200:
            break
        day += 1
        for action, params in plan.get(day, []):
            acted = client.post(
                f"/api/v1/games/{game_id}/action",
                json={"field_id": "field_1", "action": action, "params": params},
            )
            if acted.status_code != 200:
                raise RuntimeError(
                    f"{scenario}/{seed}: {action} day {day} failed: {acted.text}"
                )
        if resp.json()["season_complete"]:
            matured = True
            break

    harvest = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "field_1", "action": "harvest", "params": {}},
    )
    if harvest.status_code != 200:
        raise RuntimeError(f"{scenario}/{seed}: harvest failed: {harvest.text}")
    body = harvest.json()

    ledger = session.ledger
    row: dict[str, float] = {
        "matured": 1.0 if matured else 0.0,
        "grain_g_m2": float(body["grain_g_m2"]),
        "revenue": float(ledger.season_revenue),
        "costs": float(ledger.season_costs),
        "margin": float(ledger.season_profit),
    }
    for category in CATEGORIES:
        row[category] = float(
            sum(c.amount_credits for c in ledger.costs if c.category == category)
        )
    del games[game_id]
    return row


def _mean_rows(rows: list[dict[str, float]]) -> dict[str, float]:
    return {k: statistics.fmean([r[k] for r in rows]) for k in rows[0]}


def _format_table(results: dict[str, dict[str, float]]) -> str:
    header = (
        ["scenario", "matured", "grain g/m2", "revenue"]
        + [f"{c} cost" for c in CATEGORIES]
        + ["total cost", "margin"]
    )
    lines = ["| " + " | ".join(header) + " |"]
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for name, row in results.items():
        cells = [
            name,
            f"{row['matured'] * 100:.0f}%",
            f"{row['grain_g_m2']:.0f}",
            f"{row['revenue']:.0f}",
        ]
        cells += [f"{row[c]:.0f}" for c in CATEGORIES]
        cells += [f"{row['costs']:.0f}", f"{row['margin']:+.0f}"]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run every catalog scenario over every seed and print the margin table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help="Limit to one or more scenarios (default: all).",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=list(SEEDS),
        help="Weather seeds to average over.",
    )
    args = parser.parse_args(argv)

    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app

    client = TestClient(create_app())
    scenarios = args.scenario or sorted(SCENARIOS)

    results: dict[str, dict[str, float]] = {}
    for scenario in scenarios:
        rows = [run_scenario(client, scenario, seed) for seed in args.seeds]
        results[scenario] = _mean_rows(rows)
        print(f"  ... {scenario} done", file=sys.stderr)

    print(f"\nMean over seeds {args.seeds}, per hectare, credits.\n")
    print(_format_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
