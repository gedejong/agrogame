from __future__ import annotations

from pathlib import Path

import yaml

from agrogame.config.validation import validate_data
from agrogame.config.compose import deep_merge_dicts, load_and_compose


def test_validate_crop_sample() -> None:
    data = yaml.safe_load(Path("samples/crops.yaml").read_text())
    validate_data(data, "crop")


def test_validate_soils_sample() -> None:
    data = yaml.safe_load(Path("soils/presets.yaml").read_text())
    validate_data(data, "soil")


def test_deep_merge_simple() -> None:
    a = {"a": 1, "b": {"x": 1, "y": 2}, "c": [1, 2]}
    b = {"b": {"y": 3, "z": 4}, "c": [3], "d": 5}
    m = deep_merge_dicts(a, b)
    assert m["a"] == 1
    assert m["b"] == {"x": 1, "y": 3, "z": 4}
    assert m["c"] == [3]
    assert m["d"] == 5


def test_load_and_compose(tmp_path: Path) -> None:
    p1 = tmp_path / "a.yaml"
    p2 = tmp_path / "b.yaml"
    p1.write_text("a: 1\nb:\n  x: 1\n  y: 2\n")
    p2.write_text("b:\n  y: 3\n  z: 4\n")
    data = load_and_compose([p1, p2])
    assert data == {"a": 1, "b": {"x": 1, "y": 3, "z": 4}}
