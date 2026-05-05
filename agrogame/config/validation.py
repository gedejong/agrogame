from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import yaml
from jsonschema import Draft7Validator, RefResolver
from jsonschema.exceptions import ValidationError


SCHEMA_DIR = Path(__file__).parent / "schemas"


def get_schema_path(name: str) -> Path:
    return SCHEMA_DIR / f"{name}.json"


def _load_schema(name: str) -> dict[str, Any]:
    schema_path = get_schema_path(name)
    with schema_path.open("r", encoding="utf-8") as f:
        return cast(dict[str, Any], json.load(f))


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        with path.open("r", encoding="utf-8") as f:
            return cast(dict[str, Any], yaml.safe_load(f) or {})
    if path.suffix.lower() == ".json":
        return cast(dict[str, Any], json.loads(path.read_text()))
    raise ValueError(f"Unsupported config type: {path.suffix}")


def validate_data(data: dict[str, Any], schema_name: str) -> None:
    """Validate a configuration dictionary against a named JSON Schema.

    Raises ValidationError with rich message indicating the path and context.
    """
    base_schema = _load_schema(schema_name)
    resolver = RefResolver(
        base_uri=str(SCHEMA_DIR.resolve().as_uri()) + "/", referrer=base_schema
    )
    validator = Draft7Validator(base_schema, resolver=resolver)
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        e = errors[0]
        loc = "/".join([str(p) for p in e.absolute_path]) or "<root>"
        raise ValidationError(f"{schema_name} validation failed at {loc}: {e.message}")


def validate_file(path: Path, schema_name: str) -> dict[str, Any]:
    data = _load_yaml_or_json(path)
    validate_data(data, schema_name)
    return data
