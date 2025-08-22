from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from agrogame.soil.models import SoilLibrary


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_soil_presets(path: Path) -> SoilLibrary:
    data = load_yaml(path)
    return SoilLibrary.model_validate(data)
