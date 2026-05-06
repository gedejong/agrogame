"""Tests for config validation, compose, and watcher modules."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agrogame.config.validation import validate_file, _load_yaml_or_json
from agrogame.config.compose import _load


# ---------------------------------------------------------------------------
# validation.py — _load_yaml_or_json unsupported extension (lines 26-31)
# ---------------------------------------------------------------------------


def test_load_yaml_or_json_unsupported(tmp_path: Path) -> None:
    """Cover lines 26-31: unsupported suffix raises ValueError."""
    p = tmp_path / "data.xml"
    p.write_text("<root/>")
    with pytest.raises(ValueError, match="Unsupported config type"):
        _load_yaml_or_json(p)


def test_load_yaml_or_json_json(tmp_path: Path) -> None:
    """Cover line 30: JSON loading path."""
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"key": "value"}))
    data = _load_yaml_or_json(p)
    assert data == {"key": "value"}


# ---------------------------------------------------------------------------
# validation.py — validate_file (lines 52-54)
# ---------------------------------------------------------------------------


def test_validate_file_yaml(tmp_path: Path) -> None:
    """Cover lines 52-54 of validate_file."""
    import yaml

    p = tmp_path / "crop.yaml"
    # Load a valid sample to re-use
    sample = yaml.safe_load(Path("data/samples/crops.yaml").read_text())
    p.write_text(yaml.dump(sample))
    result = validate_file(p, "crop")
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# compose.py — _load unsupported extension (line 33)
# ---------------------------------------------------------------------------


def test_compose_load_unsupported(tmp_path: Path) -> None:
    """Cover line 33 in compose._load."""
    p = tmp_path / "data.toml"
    p.write_text("key = 'value'")
    with pytest.raises(ValueError, match="Unsupported config type"):
        _load(p)


def test_compose_load_json(tmp_path: Path) -> None:
    """Cover line 32 in compose._load (JSON path)."""
    p = tmp_path / "data.json"
    p.write_text(json.dumps({"a": 1}))
    result = _load(p)
    assert result == {"a": 1}


# ---------------------------------------------------------------------------
# watcher.py — watch function (lines 29-34)
# ---------------------------------------------------------------------------


def test_watch_starts_observer() -> None:
    """Cover lines 29-34 in watcher.watch.

    Regression note (#304): `mock.patch("agrogame.config.watcher.X")`
    walks the dotted path via `getattr` and only re-imports
    `agrogame.config` if it isn't already in `sys.modules`. Earlier tests
    that mutate `sys.modules["agrogame"]` without restoring its
    descendants (notably `tests/test_check_docs_coverage.py::
    test_key_classes_must_be_importable`) used to leave a freshly-
    imported `agrogame` without `config` bound as an attribute, breaking
    this patch on Python 3.10. The snapshot/restore in that test fixed
    the pollution at source — keep it that way.
    """
    from agrogame.config.watcher import watch

    with patch("agrogame.config.watcher.WatchdogObserver") as MockObs:
        mock_instance = MagicMock()
        MockObs.return_value = mock_instance
        observer = watch([Path("/tmp")], lambda _: None)
        mock_instance.schedule.assert_called_once()
        mock_instance.start.assert_called_once()
        assert observer is mock_instance
