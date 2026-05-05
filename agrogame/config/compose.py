from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast
from collections.abc import Iterable

import yaml


def deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge override into base without mutating inputs.

    - Dicts are merged recursively
    - Lists are replaced (simple, predictable semantics)
    - Scalars are overwritten by override
    """
    result = deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge_dicts(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def _load(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        with path.open("r", encoding="utf-8") as f:
            return cast(dict[str, Any], yaml.safe_load(f) or {})
    if path.suffix.lower() == ".json":
        return cast(dict[str, Any], json.loads(path.read_text()))
    raise ValueError(f"Unsupported config type: {path}")


def load_and_compose(paths: Iterable[Path]) -> dict[str, Any]:
    """Load multiple files and compose via deep-merge in order.

    Later files override earlier files.
    """
    data: dict[str, Any] = {}
    for p in paths:
        data = deep_merge_dicts(data, _load(p))
    return data
