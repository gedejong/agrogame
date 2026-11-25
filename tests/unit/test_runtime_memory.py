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


# #583: every memory holder's (soil-owned, crop-owned) names. Soil-owned memory
# survives ``reset_crop``; crop-owned memory resets with the crop it mirrors.
# Adding, removing or reclassifying a ``_MEMORY`` name must change this table.
_CANOPY = (
    "_last_water _last_n _last_p _last_fe _last_zn _last_mn _last_s "
    "_stress_history _consecutive_wilt_days _consecutive_waterlog_days "
    "_waterlogged_today _root_depth_cm"
)
_CLASSIFICATION: dict[str, tuple[str, str]] = {
    "FullSimulationOrchestrator": (
        "_co2_buffer",
        "_last_biomass_inc_g_m2 _pending_root_canopy_inc_g_m2",
    ),
    "ETRuntime": ("_evap_state _residue", ""),
    "CanopyRuntime": ("", _CANOPY),
    "AggregationRuntime": (
        "_day_count _prev_wfps _was_dry _was_frozen _fungal_fractions",
        "_root_fractions",
    ),
    "SOMRuntime": ("_prev_wfps _was_dry som", "_root_fracs _root_fracs_smoothed"),
    "ThreePoolSOM": ("_disruption_days", ""),
    "MicrobesRuntime": (
        "_daily_enzyme_totals",
        "_root_fractions _root_fractions_smoothed",
    ),
    "MicronutrientRuntime": ("", "_last_biomass_inc _root_fractions"),
    "MicronutrientCycle": ("_env _som_c_by_layer _last_eh_by_layer", ""),
    "NitrogenRuntime": ("_eh_by_layer", ""),
    "NitrogenCycle": (
        "_env _som_mineralized_n _aerobic_fraction_override _pending_h_kmol_ha",
        "_massflow_supply_by_layer _plant_uptake_kg_ha",
    ),
    "RedoxRuntime": ("_pre_drainage_theta", "_root_fractions"),
    "EnvironmentalCache": (
        "ph_by_layer microbe_activity_by_layer fungal_fraction_by_layer",
        "root_fractions",
    ),
    "PhosphorusCycle": ("_slow_release_schedules _env", ""),
    "SulfurCycle": ("_slow_release_schedules _env", ""),
}


def _engine_holders() -> dict[str, type]:
    """Every ``RuntimeMemory`` subclass defined in the engine (not in tests)."""
    found, todo = {}, list(RuntimeMemory.__subclasses__())
    while todo:
        cls = todo.pop()
        todo.extend(cls.__subclasses__())
        if cls.__module__.startswith("agrogame."):
            found[cls.__name__] = cls
    return found


def test_583_soil_and_crop_memory_classification_is_pinned() -> None:
    holders = _engine_holders()
    assert set(holders) == set(_CLASSIFICATION)
    for name, (soil, crop) in _CLASSIFICATION.items():
        soil_names, crop_names = set(soil.split()), set(crop.split())
        assert not soil_names & crop_names, name
        assert set(holders[name]._MEMORY) == soil_names | crop_names, name
        assert set(holders[name]._CROP_MEMORY) == crop_names, name


def test_583_a_crop_owned_name_outside_memory_is_rejected() -> None:
    with pytest.raises(ValueError, match=r"_CROP_MEMORY not in _MEMORY: \['_y'\]"):

        class _Bad(RuntimeMemory):
            _MEMORY = ("_x",)
            _CROP_MEMORY = ("_y",)


class _SoilInner(RuntimeMemory):
    _MEMORY = ("ph", "roots")
    _CROP_MEMORY = ("roots",)

    def __init__(self) -> None:
        self.ph, self.roots = [6.5], [0.7, 0.3]


class _SoilHolder(RuntimeMemory):
    _MEMORY = ("clock", "growth", "env")
    _CROP_MEMORY = ("growth",)

    def __init__(self) -> None:
        self.clock, self.growth, self.env = 4.5, 1.25, _SoilInner()


def test_583_soil_only_drops_crop_names_in_nested_holders() -> None:
    holder = _SoilHolder()
    assert holder.memory_to_dict(soil_only=True) == {"clock": 4.5, "env": {"ph": [6.5]}}
    full = holder.memory_to_dict()
    assert full["growth"] == 1.25 and full["env"]["roots"] == [0.7, 0.3]
    fresh = _SoilHolder()
    fresh.clock, fresh.env.ph[:] = 0.0, [7.0]
    fresh.growth, fresh.env.roots[:] = 0.0, [1.0]
    fresh.restore_memory(holder.memory_to_dict(soil_only=True))
    assert (fresh.clock, fresh.env.ph) == (4.5, [6.5])  # soil-owned: restored
    assert (fresh.growth, fresh.env.roots) == (0.0, [1.0])  # crop-owned: kept


def test_583_som_soil_memory_keeps_cumulative_co2() -> None:
    som = ThreePoolSOM(SOMPoolParams(), n_layers=2)
    som.state.layers[0].cumulative_co2_c_kg_ha = 1.5
    assert som.memory_to_dict(soil_only=True) == som.memory_to_dict()
