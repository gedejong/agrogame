from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import CropParameterLibrary


def load_library(path: str | Path) -> CropParameterLibrary:
    with open(path, "r", encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    return CropParameterLibrary.model_validate(data)
