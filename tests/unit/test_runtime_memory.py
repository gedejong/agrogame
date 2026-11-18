"""The runtime-memory helper: JSON-native dump and in-place restore (#577)."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, ClassVar

import pytest

from agrogame.params.memory import RuntimeMemory, to_json_native
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.som.pools import SOMPoolParams, ThreePoolSOM


@dataclass
class _Record:
    days: int
    amount: float


class _Inner(RuntimeMemory):
    _MEMORY = ("values",)

    def __init__(self) -> None:
        self.values = [1.0, 2.0]


class _Holder(RuntimeMemory):
    _MEMORY = ("window", "cache", "record", "inner", "optional", "count", "pending")
    _MEMORY_RECORDS: ClassVar[dict[str, type]] = {"pending": _Record}

    def __init__(self) -> None:
        self.window: deque[float] = deque([0.5], maxlen=3)
        self.cache: dict[str, float] = {"urease": 0.1}
        self.record = _Record(days=0, amount=0.0)
        self.inner = _Inner()
        self.alias = self.inner.values  # another holder of the same list
        self.optional: list[float] | None = None
        self.count = 0
        self.pending: list[list[_Record]] = [[], []]


def _filled() -> _Holder:
    h = _Holder()
    h.window.extend([0.7, 0.9])
    h.cache["protease"] = 0.2
    h.record.days, h.record.amount = 4, 1.5
    h.inner.values[:] = [3.0, 4.0]
    h.optional, h.count = [0.25, 0.75], 7
    h.pending[1].append(_Record(days=30, amount=12.5))
    return h


def test_memory_dumps_to_json_native_types() -> None:
    data = _filled().memory_to_dict()
    assert data == json.loads(json.dumps(data))  # strict: no default=
    assert data["window"] == [0.5, 0.7, 0.9]
    assert data["record"] == {"days": 4, "amount": 1.5}
    assert data["inner"] == {"values": [3.0, 4.0]}
    assert data["pending"] == [[], [{"days": 30, "amount": 12.5}]]


def test_restore_writes_in_place_and_keeps_aliases() -> None:
    target = _Holder()
    window, cache, record = target.window, target.cache, target.record
    values = target.inner.values
    target.restore_memory(json.loads(json.dumps(_filled().memory_to_dict())))
    assert target.window is window and list(window) == [0.5, 0.7, 0.9]
    assert window.maxlen == 3
    assert target.cache is cache and cache == {"urease": 0.1, "protease": 0.2}
    assert target.record is record and (record.days, record.amount) == (4, 1.5)
    assert target.inner.values is values is target.alias
    assert values == [3.0, 4.0]
    assert (target.optional, target.count) == ([0.25, 0.75], 7)
    assert target.pending == [[], [_Record(days=30, amount=12.5)]]


def test_restore_copies_the_payload_and_skips_absent_names() -> None:
    payload: dict[str, Any] = {
        "optional": [1.0],
        "pending": [[{"days": 1, "amount": 2.0}]],
    }
    target = _Holder()
    target.restore_memory(payload)
    payload["optional"].append(9.0)
    assert target.optional == [1.0]  # not the payload's list
    assert list(target.window) == [0.5] and target.count == 0  # absent: unchanged
    target.restore_memory({"optional": None})
    assert target.optional is None


class _Colour(Enum):
    RED = 1


@pytest.mark.parametrize("value", [_Colour.RED, object(), {1: 0.5}, {"a": object()}])
def test_values_without_a_json_form_raise(value: Any) -> None:
    with pytest.raises(ValueError, match="runtime memory"):
        to_json_native(value)


@pytest.mark.parametrize(
    ("name", "saved"),
    [
        ("window", {"a": 1.0}),
        ("cache", [1.0]),
        ("record", [4, 1.5]),
        ("record", {"days": 1, "colour": "red"}),
        ("count", [1, 2]),
        ("inner", [3.0]),
    ],
)
def test_restore_rejects_a_mismatched_shape(name: str, saved: Any) -> None:
    with pytest.raises(ValueError):
        _Holder().restore_memory({name: saved})


def test_som_memory_carries_cumulative_co2_per_layer() -> None:
    som = ThreePoolSOM(SOMPoolParams(), n_layers=2)
    som.state.layers[1].cumulative_co2_c_kg_ha = 3.5
    som.apply_wet_dry_disruption(0)
    target = ThreePoolSOM(SOMPoolParams(), n_layers=2)
    target.restore_memory(som.memory_to_dict())
    assert target._disruption_days == som._disruption_days != [0, 0]
    assert [ly.cumulative_co2_c_kg_ha for ly in target.state.layers] == [0.0, 3.5]
    with pytest.raises(ValueError, match="cumulative_co2_c_kg_ha"):
        target.restore_memory({"cumulative_co2_c_kg_ha": [1.0]})


def _orchestrator() -> FullSimulationOrchestrator:
    soils = load_soil_presets(Path("soils/presets.yaml"))
    return FullSimulationOrchestrator(soils.soils["loam_temperate"])


def test_orchestrator_rejects_two_holders_of_one_class() -> None:
    orch = _orchestrator()
    orch._runtimes.append(orch._runtimes[-1])
    with pytest.raises(ValueError, match="two memory holders"):
        orch.runtime_memory_to_dict()


def test_orchestrator_ignores_an_owner_this_build_lacks() -> None:
    orch = _orchestrator()
    memory = orch.runtime_memory_to_dict()
    memory["FutureRuntime"] = {"_x": 1}
    memory["FullSimulationOrchestrator"]["_last_biomass_inc_g_m2"] = 2.5
    orch.restore_runtime_memory(memory)
    assert orch._last_biomass_inc_g_m2 == 2.5
