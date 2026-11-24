"""Cross-day runtime memory: declare it, save it JSON-native, restore it in place.

Runtimes, nutrient cycles and the orchestrator carry values from one day to
the next outside every ``*State`` container: the Ritchie (1972) stage-2
evaporation clock, the running-mean stress window, the weekly aggregation
cadence, unreleased slow-release fertiliser. That memory is simulation state,
so a save must carry it or a load does not continue the run it came from
(#577). A class lists such attributes in ``_MEMORY`` and inherits
:class:`RuntimeMemory`.

The same memory decides what a crop change keeps (#583). ``_CROP_MEMORY``
names the subset that mirrors the crop's own state (root fractions, canopy
stress history, yesterday's growth); its source is rebuilt with the crop, so it
resets. Every other name is soil-owned and ``reset_crop`` carries it across, as
APSIM keeps its soil modules through sowing and harvest (Keating et al. 2003,
Eur. J. Agron. 18:267-288).

Two rules make a restore exact:

- **JSON-native payload.** :func:`to_json_native` turns a deque or tuple into a
  list and a dataclass into a dict, and raises on anything without a JSON form,
  because the API save path serialises with ``default=str`` and would
  otherwise stringify the object without an error.
- **In place, never rebound.** Other objects alias some of this memory
  (``MicronutrientCycle._ph_by_layer`` *is* its cache's ``ph_by_layer``), so a
  restore writes into the existing list, deque, dict or dataclass. A rebound
  alias decouples silently; #515 measured 30% grain error from one.

This module imports only the standard library, so every layer may use it
(ADR-008).
"""

from __future__ import annotations

import dataclasses
from collections import deque
from collections.abc import Mapping
from typing import Any, ClassVar

_SCALARS = (bool, int, float, str)


class RuntimeMemory:
    """Mixin for a class whose ``_MEMORY`` attributes persist from day to day.

    ``_MEMORY`` names the attributes. An attribute holding another
    ``RuntimeMemory`` (a cycle's environmental cache) nests that object's own
    memory. ``_MEMORY_RECORDS`` maps an attribute to the dataclass its saved
    records decode into, for memory that holds records rather than numbers.
    ``_CROP_MEMORY`` is the subset a crop change resets (#583); a nested
    holder classifies its own names.
    """

    _MEMORY: ClassVar[tuple[str, ...]] = ()
    _CROP_MEMORY: ClassVar[tuple[str, ...]] = ()
    _MEMORY_RECORDS: ClassVar[Mapping[str, type]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Reject a crop-owned name that is not declared memory."""
        super().__init_subclass__(**kwargs)
        undeclared = sorted(set(cls._CROP_MEMORY) - set(cls._MEMORY))
        if undeclared:
            raise ValueError(
                f"{cls.__name__}: _CROP_MEMORY not in _MEMORY: {undeclared}"
            )

    def memory_to_dict(self, *, soil_only: bool = False) -> dict[str, Any]:
        """Return the declared memory as JSON-native values.

        ``soil_only`` leaves out the crop-owned names, here and in every nested
        holder: the memory ``reset_crop`` carries across (#583).
        """
        names = [n for n in self._MEMORY if not (soil_only and n in self._CROP_MEMORY)]
        return {name: _dump(getattr(self, name), soil_only) for name in names}

    def restore_memory(self, data: Mapping[str, Any]) -> None:
        """Write saved memory into the existing objects (#577).

        A name absent from ``data`` keeps its current value, so a save that
        predates an attribute restores the rest.
        """
        for name in self._MEMORY:
            if name in data:
                record = self._MEMORY_RECORDS.get(name)
                _restore_attr(self, name, _decode(data[name], record))


def _dump(value: Any, soil_only: bool) -> Any:
    """One memory attribute, passing ``soil_only`` to a nested holder."""
    if isinstance(value, RuntimeMemory):
        return value.memory_to_dict(soil_only=soil_only)
    return to_json_native(value)


def to_json_native(value: Any) -> Any:
    """Convert runtime memory to ``None``, scalars, lists and str-keyed dicts."""
    if value is None or type(value) in _SCALARS:
        return value
    if isinstance(value, RuntimeMemory):
        return value.memory_to_dict()
    if isinstance(value, list | tuple | deque):
        return [to_json_native(item) for item in value]
    if isinstance(value, dict):
        return _dict_to_json(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _dict_to_json(
            {f.name: getattr(value, f.name) for f in dataclasses.fields(value)}
        )
    raise ValueError(f"runtime memory holds a {type(value).__name__}: no JSON form")


def _dict_to_json(value: dict[Any, Any]) -> dict[str, Any]:
    if not all(type(key) is str for key in value):
        raise ValueError(f"runtime memory dict keys must be str: {list(value)!r}")
    return {key: to_json_native(item) for key, item in value.items()}


def _decode(saved: Any, record: type | None) -> Any:
    """Copy a saved value, building ``record`` instances from its dicts.

    Lists and dicts are rebuilt so the restored state never shares a
    container with the payload it was loaded from.
    """
    if isinstance(saved, list):
        return [_decode(item, record) for item in saved]
    if isinstance(saved, dict):
        if record is not None:
            return record(**saved)
        return {key: _decode(item, None) for key, item in saved.items()}
    return saved


def _expect(value: Any, kind: type, owner: object, name: str) -> Any:
    if not isinstance(value, kind):
        raise ValueError(
            f"{type(owner).__name__}.{name}: saved memory is a "
            f"{type(value).__name__}, expected {kind.__name__}"
        )
    return value


def _restore_attr(owner: object, name: str, value: Any) -> None:
    """Restore one attribute, writing into the live container when there is one."""
    current = getattr(owner, name)
    if isinstance(current, RuntimeMemory):
        current.restore_memory(_expect(value, dict, owner, name))
    elif value is None or current is None:
        setattr(owner, name, value)
    elif isinstance(current, deque):
        items = _expect(value, list, owner, name)
        current.clear()
        current.extend(items)
    elif isinstance(current, list):
        current[:] = _expect(value, list, owner, name)
    elif isinstance(current, dict):
        current.clear()
        current.update(_expect(value, dict, owner, name))
    elif dataclasses.is_dataclass(current):
        _restore_dataclass(current, _expect(value, dict, owner, name))
    elif type(current) in _SCALARS and type(value) in _SCALARS:
        setattr(owner, name, value)
    else:
        raise ValueError(
            f"{type(owner).__name__}.{name}: cannot restore a "
            f"{type(value).__name__} over a {type(current).__name__}"
        )


def _restore_dataclass(target: Any, saved: dict[str, Any]) -> None:
    names = {f.name for f in dataclasses.fields(target)}
    unknown = sorted(set(saved) - names)
    if unknown:
        raise ValueError(f"{type(target).__name__}: unknown saved fields {unknown}")
    for key, item in saved.items():
        _restore_attr(target, key, item)
