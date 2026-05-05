from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from agrogame.config.validation import validate_data

from .models import CropParameterLibrary


def load_library(path: str | Path) -> CropParameterLibrary:
    with open(path, encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    # Validate against JSON Schema before Pydantic model validation
    if isinstance(path, str):
        p = Path(path)
    else:
        p = path
    if p.suffix.lower() in {".yaml", ".yml", ".json"}:
        validate_data(data, "crop")
    return CropParameterLibrary.model_validate(data)
