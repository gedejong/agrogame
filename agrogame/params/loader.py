from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import ParameterLibrary


def load_library(path: str | Path) -> ParameterLibrary:
    with open(path, "r", encoding="utf-8") as f:
        data: Any = yaml.safe_load(f)
    return ParameterLibrary.model_validate(data)
