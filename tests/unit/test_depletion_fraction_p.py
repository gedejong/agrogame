"""Per-crop depletion fraction p for the root-zone water gauge (#660, #639).

FAO-56 Table 22 (Allen et al. 1998), soil water depletion fraction for no
stress: maize, sorghum, spring and winter wheat 0.55; soybeans 0.50; rice 0.20
(footnote 4, "of saturation", applied to TAW on the free-draining bucket);
grapes, wine 0.45. Display only: the API reports it and no engine module
reads it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets

FAO56_TABLE_22_P = {
    "maize": 0.55,
    "sorghum": 0.55,
    "spring_wheat": 0.55,
    "winter_wheat": 0.55,
    "soybean": 0.50,
    "rice": 0.20,
    "grape": 0.45,
}


def test_every_crop_carries_its_table_22_p() -> None:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    assert {k: c.depletion_fraction_p for k, c in crops.crops.items()} == (
        FAO56_TABLE_22_P
    )


@pytest.mark.parametrize("crop", sorted(FAO56_TABLE_22_P))
def test_each_value_cites_table_22(crop: str) -> None:
    text = Path("data/crops/presets.yaml").read_text(encoding="utf-8")
    block = text.split(f"\n  {crop}:\n", 1)[1]
    assert "FAO-56 Table 22" in block.split("depletion_fraction_p:", 1)[0], crop


def test_climate_overrides_keep_p() -> None:
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    for crop, by_climate in lib.climate_overrides.items():
        for preset in by_climate.values():
            assert preset.depletion_fraction_p == FAO56_TABLE_22_P[crop]


def test_no_engine_module_reads_p() -> None:
    """Outside the API layer only the preset loader names it (B6)."""
    readers = {
        str(path)
        for path in Path("agrogame").rglob("*.py")
        if path.parts[1] != "api"
        and re.search(r"\bdepletion_fraction_p\b", path.read_text(encoding="utf-8"))
    }
    assert readers == {"agrogame/plant/presets.py"}
