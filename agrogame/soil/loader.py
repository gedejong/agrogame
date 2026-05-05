from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from agrogame.soil.models import SoilLibrary
from agrogame.config.validation import validate_data


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_soil_presets(path: Path) -> SoilLibrary:
    # Support new normalized data location with fallback for backward compatibility
    candidate = path
    if not candidate.exists():
        alt = Path("data/soils/presets.yaml")
        candidate = alt if alt.exists() else path
    data = load_yaml(candidate)
    # Validate against JSON Schema before Pydantic
    validate_data(data, "soil")
    return SoilLibrary.model_validate(data)
