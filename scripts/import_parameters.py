from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import yaml

from agrogame.params.models import (
    Biomass,
    CropParameterLibrary,
    CropParameters,
    Roots,
    ThermalTime,
)


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def try_parse_our_schema(payload: Dict[str, Any]) -> Dict[str, CropParameters]:
    crops: Dict[str, CropParameters] = {}
    if "crops" in payload and isinstance(payload["crops"], dict):
        for key, value in payload["crops"].items():
            try:
                crops[key] = CropParameters.model_validate(value)
            except Exception:
                # Not our schema
                continue
    return crops


def merge_libraries(existing: CropParameterLibrary, incoming: Dict[str, CropParameters]) -> CropParameterLibrary:
    merged: Dict[str, CropParameters] = dict(existing.crops)
    for name, params in incoming.items():
        # Prefer incoming; overwrite if exists
        merged[name] = params
    return CropParameterLibrary(crops=merged)


def import_from_directory(path: Path) -> Dict[str, CropParameters]:
    """
    Import crop parameters from a directory by:
    1) Merging any files already in our schema (contain top-level 'crops')
    2) Attempting basic adapters for simple JSON/YAML with familiar keys
    """
    collected: Dict[str, CropParameters] = {}
    for file in path.rglob("*"):
        if not file.is_file():
            continue
        try:
            if file.suffix.lower() in {".yaml", ".yml"}:
                payload = load_yaml(file)
            elif file.suffix.lower() in {".json"}:
                payload = json.loads(file.read_text(encoding="utf-8"))
            else:
                continue
        except Exception:
            continue

        # Strategy 1: our schema
        crops = try_parse_our_schema(payload)
        if crops:
            collected.update(crops)
            continue

        # Strategy 2: simple flat mapping heuristic (PCSE/APSIM-lite)
        # Expected example:
        # {
        #   "name": "rice",
        #   "thermal_time": {"base_temp_c": 8, "emergence_dd": 100, ...},
        #   "roots": {"max_depth_cm": 120, "growth_rate_cm_per_day": 2, "distribution": [0.5,0.3,0.2]},
        #   "biomass": {"rue_g_per_mj": 2.7, "harvest_index": 0.5, ...}
        # }
        try:
            cp = CropParameters.model_validate(payload)
            collected[cp.name] = cp
            continue
        except Exception:
            pass

        # Strategy 3: PCSE/APSIM minimal key mapping (very limited)
        # PCSE/WOFOST sometimes uses keys like TBASE, TSUM1, TSUM2
        # APSIM may provide JSON with RootDepth, RUE, HI
        try:
            name = payload.get("name") or payload.get("crop")
            if not isinstance(name, str):
                continue
            # Thermal time
            tt = ThermalTime(
                base_temp_c=float(payload.get("TBASE", payload.get("base_temp_c", 8.0))),
                emergence_dd=float(payload.get("TSUM_EMERG", payload.get("emergence_dd", 100)) ),
                flowering_dd=float(payload.get("TSUM1", payload.get("flowering_dd", 900))),
                maturity_dd=float(payload.get("TSUM2", payload.get("maturity_dd", 1700))),
            )
            # Roots
            roots = Roots(
                max_depth_cm=float(payload.get("MaxRootDepth", payload.get("max_depth_cm", 120))),
                growth_rate_cm_per_day=float(payload.get("RootGrowthRate", payload.get("growth_rate_cm_per_day", 2.0))),
                distribution=list(payload.get("RootDistribution", payload.get("distribution", [0.5, 0.3, 0.2]))),
            )
            # Biomass
            biomass = Biomass(
                rue_g_per_mj=float(payload.get("RUE", payload.get("rue_g_per_mj", 2.8))),
                harvest_index=float(payload.get("HI", payload.get("harvest_index", 0.5))),
                partition_vegetative=dict(payload.get("partition_vegetative", {"leaf": 0.6, "stem": 0.2, "root": 0.2})),
                partition_reproductive=dict(payload.get("partition_reproductive", {"leaf": 0.2, "stem": 0.2, "grain": 0.6})),
            )
            collected[name] = CropParameters(name=name, thermal_time=tt, roots=roots, biomass=biomass)
        except Exception:
            # Skip unknown formats silently
            continue

    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Import crop parameters into samples/crops.yaml")
    parser.add_argument("--pcse-path", type=Path, help="Path to a local clone of ajwdewit/pcse", required=False)
    parser.add_argument("--apsim-path", type=Path, help="Path to a local clone of APSIMInitiative/APSIM-Crop-Codes", required=False)
    parser.add_argument("--output", type=Path, default=Path("samples/crops.yaml"), help="Output YAML file (merged)")
    parser.add_argument("--dry-run", action="store_true", help="Do not write output; just validate and report counts")
    args = parser.parse_args()

    # Load existing library if present
    if args.output.exists():
        try:
            existing = CropParameterLibrary.model_validate(load_yaml(args.output))
        except Exception:
            existing = CropParameterLibrary(crops={})
    else:
        existing = CropParameterLibrary(crops={})

    incoming: Dict[str, CropParameters] = {}
    if args.pcse_path and args.pcse_path.exists():
        incoming.update(import_from_directory(args.pcse_path))
    if args.apsim_path and args.apsim_path.exists():
        incoming.update(import_from_directory(args.apsim_path))

    if not incoming:
        print("No parameters discovered. Provide --pcse-path / --apsim-path pointing to repositories.")
        return

    merged = merge_libraries(existing, incoming)
    print(f"Collected {len(incoming)} crops; merged library now has {len(merged.crops)} crops.")

    if args.dry_run:
        # Validate serialization and exit
        _payload = merged.model_dump(mode="json")
        yaml.safe_dump(_payload, allow_unicode=True)
        return

    save_yaml(merged.model_dump(mode="json"), args.output)
    print(f"Wrote merged parameters to {args.output}")


if __name__ == "__main__":
    main()


