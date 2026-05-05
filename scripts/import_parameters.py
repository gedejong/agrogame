from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml
import subprocess
from pydantic import ValidationError as PydanticValidationError
from jsonschema.exceptions import ValidationError as JSONSchemaValidationError

from agrogame.params.models import (
    Biomass,
    CropParameterLibrary,
    CropParameters,
    Roots,
    ThermalTime,
)
from agrogame.config.validation import validate_data


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_yaml(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def try_parse_our_schema(payload: dict[str, Any]) -> dict[str, CropParameters]:
    crops: dict[str, CropParameters] = {}
    if "crops" in payload and isinstance(payload["crops"], dict):
        # Validate full library against JSON Schema first
        try:
            validate_data(payload, "crop")
        except JSONSchemaValidationError:
            # Not our schema
            return {}
        # Then coerce to models
        for key, value in payload["crops"].items():
            crops[key] = CropParameters.model_validate(value)
    return crops


def merge_libraries(
    existing: CropParameterLibrary, incoming: dict[str, CropParameters]
) -> CropParameterLibrary:
    merged: dict[str, CropParameters] = dict(existing.crops)
    for name, params in incoming.items():
        # Prefer incoming; overwrite if exists
        merged[name] = params
    return CropParameterLibrary(crops=merged)


def _parse_pcse_crop_file(path: Path) -> CropParameters | None:
    """Parse a minimal subset of PCSE .crop files (key=value lines).

    Extracts: name (from filename), TBASE, TSUM1, TSUM2, TSUMEM if present.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError) as e:
        raise RuntimeError(f"Failed reading PCSE crop file {path}") from e
    kv: dict[str, float] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline comments starting with ! or #
        for token in ("!", "#"):
            if token in line:
                line = line.split(token, 1)[0].strip()
        if "=" not in line:
            continue
        key, val = (p.strip() for p in line.split("=", 1))
        try:
            kv[key.upper()] = float(val)
        except ValueError:
            continue
    if not kv:
        raise ValueError(f"No key=value parameters parsed from {path}")
    name = path.stem.replace(".crop", "").replace("wofost_", "").replace("lintul3_", "")
    base_temp = float(kv.get("TBASE", 8.0))
    emer = float(kv.get("TSUMEM", kv.get("TSUM_EMERG", 100.0)))
    tsum1 = float(kv.get("TSUM1", 900.0))
    tsum2 = float(kv.get("TSUM2", 1700.0))
    # Guard against zeros/negatives in source files
    if emer <= 0:
        emer = 100.0
    if tsum1 <= 0:
        tsum1 = 900.0
    if tsum2 <= 0:
        tsum2 = 1700.0
    tt = ThermalTime(
        base_temp_c=base_temp,
        emergence_dd=emer,
        flowering_dd=tsum1,
        maturity_dd=tsum2,
    )
    roots = Roots(
        max_depth_cm=120.0,
        growth_rate_cm_per_day=2.0,
        distribution=[0.5, 0.3, 0.2],
    )
    biomass = Biomass(
        rue_g_per_mj=kv.get("RUE", 2.8),
        harvest_index=kv.get("HI", 0.5),
        partition_vegetative={"leaf": 0.6, "stem": 0.2, "root": 0.2},
        partition_reproductive={"leaf": 0.2, "stem": 0.2, "grain": 0.6},
    )
    try:
        return CropParameters(name=name, thermal_time=tt, roots=roots, biomass=biomass)
    except PydanticValidationError as e:
        raise ValueError(f"Invalid crop parameters synthesized from {path}") from e


def import_from_directory(path: Path) -> dict[str, CropParameters]:
    """
    Import crop parameters from a directory by:
    1) Merging any files already in our schema (contain top-level 'crops')
    2) Attempting basic adapters for simple JSON/YAML with familiar keys
    """
    collected: dict[str, CropParameters] = {}
    pcse_tests = path / "pcse" / "tests" / "test_data"
    candidate_files: list[Path] = []
    if pcse_tests.exists():
        candidate_files.extend(pcse_tests.glob("*.crop"))
        candidate_files.extend(pcse_tests.glob("*.yaml"))
    else:
        candidate_files = (
            list(path.rglob("*.yaml"))
            + list(path.rglob("*.yml"))
            + list(path.rglob("*.json"))
        )

    for file in candidate_files:
        if not file.is_file():
            continue
        # Special-case PCSE .crop files
        if file.suffix.lower() == ".crop":
            cp = _parse_pcse_crop_file(file)
            if cp is not None:
                collected[cp.name] = cp
            continue
        try:
            if file.suffix.lower() in {".yaml", ".yml"}:
                payload = load_yaml(file)
            elif file.suffix.lower() in {".json"}:
                payload = json.loads(file.read_text(encoding="utf-8"))
            else:
                continue
        except (OSError, yaml.YAMLError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to load candidate parameter file {file}") from e

        # Strategy 1: our schema
        crops = try_parse_our_schema(payload)
        if crops:
            collected.update(crops)
            continue

        # Strategy 2: simple flat mapping heuristic (PCSE/APSIM-lite)
        # Expected example (wrapped for E501):
        # {
        #   "name": "rice",
        #   "thermal_time": {"base_temp_c": 8, "emergence_dd": 100, ...},
        #   "roots": {
        #       "max_depth_cm": 120,
        #       "growth_rate_cm_per_day": 2,
        #       "distribution": [0.5, 0.3, 0.2],
        #   },
        #   "biomass": {"rue_g_per_mj": 2.7, "harvest_index": 0.5, ...}
        # }
        try:
            cp = CropParameters.model_validate(payload)
            collected[cp.name] = cp
            continue
        except PydanticValidationError:
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
                base_temp_c=float(
                    payload.get("TBASE", payload.get("base_temp_c", 8.0))
                ),
                emergence_dd=float(
                    payload.get(
                        "TSUM_EMERG",
                        payload.get("emergence_dd", 100),
                    )
                ),
                flowering_dd=float(
                    payload.get("TSUM1", payload.get("flowering_dd", 900))
                ),
                maturity_dd=float(
                    payload.get("TSUM2", payload.get("maturity_dd", 1700))
                ),
            )
            # Roots
            roots = Roots(
                max_depth_cm=float(
                    payload.get(
                        "MaxRootDepth",
                        payload.get("max_depth_cm", 120),
                    )
                ),
                growth_rate_cm_per_day=float(
                    payload.get(
                        "RootGrowthRate", payload.get("growth_rate_cm_per_day", 2.0)
                    )
                ),
                distribution=list(
                    payload.get(
                        "RootDistribution",
                        payload.get("distribution", [0.5, 0.3, 0.2]),
                    )
                ),
            )
            # Biomass
            biomass = Biomass(
                rue_g_per_mj=float(
                    payload.get("RUE", payload.get("rue_g_per_mj", 2.8))
                ),
                harvest_index=float(
                    payload.get("HI", payload.get("harvest_index", 0.5))
                ),
                partition_vegetative=dict(
                    payload.get(
                        "partition_vegetative",
                        {"leaf": 0.6, "stem": 0.2, "root": 0.2},
                    )
                ),
                partition_reproductive=dict(
                    payload.get(
                        "partition_reproductive",
                        {"leaf": 0.2, "stem": 0.2, "grain": 0.6},
                    )
                ),
            )
            collected[name] = CropParameters(
                name=name, thermal_time=tt, roots=roots, biomass=biomass
            )
        except (TypeError, ValueError, KeyError) as e:
            # Unknown format; escalate with context instead of silent skip
            raise ValueError(f"Unsupported parameter format in {file}") from e

    return collected


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import crop parameters into data/samples/crops.yaml"
    )
    parser.add_argument(
        "--pcse-path",
        type=Path,
        help="Path to a local clone of ajwdewit/pcse",
        required=False,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/samples/crops.yaml"),
        help="Output YAML file (merged)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not write output; just validate and report counts",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Clone PCSE into .cache/imports if local path not provided",
    )
    args = parser.parse_args()

    # Load existing library if present
    if args.output.exists():
        try:
            existing = CropParameterLibrary.model_validate(load_yaml(args.output))
        except Exception:
            existing = CropParameterLibrary(crops={})
    else:
        existing = CropParameterLibrary(crops={})

    incoming: dict[str, CropParameters] = {}

    def ensure_clone(url: str, dest: Path) -> Path | None:
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["git", "clone", "--depth", "1", url, str(dest)], check=True)
            return dest
        except (subprocess.CalledProcessError, OSError) as e:
            raise RuntimeError(f"Failed to clone repository {url} to {dest}") from e

    pcse_path = args.pcse_path
    cache_root = Path(".cache/imports")

    if not pcse_path and args.fetch:
        pcse_path = ensure_clone(
            "https://github.com/ajwdewit/pcse.git", cache_root / "pcse"
        )

    if pcse_path and Path(pcse_path).exists():
        incoming.update(import_from_directory(Path(pcse_path)))

    if not incoming:
        print("No parameters discovered. Provide --pcse-path pointing to a repository.")
        return

    merged = merge_libraries(existing, incoming)
    print(
        f"Collected {len(incoming)} crops; merged library now has "
        f"{len(merged.crops)} crops."
    )

    if args.dry_run:
        # Validate merged payload against schema and exit
        _payload = merged.model_dump(mode="json")
        validate_data(_payload, "crop")
        yaml.safe_dump(_payload, allow_unicode=True)
        return

    # Validate merged payload before writing
    payload = merged.model_dump(mode="json")
    validate_data(payload, "crop")
    save_yaml(payload, args.output)
    print(f"Wrote merged parameters to {args.output}")


if __name__ == "__main__":
    main()
