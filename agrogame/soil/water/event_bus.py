from __future__ import annotations

from typing import Any, Callable, DefaultDict, List, Type, TypeVar
from collections import defaultdict


T = TypeVar("T")


class EventBus:
    def __init__(self, debug_mode: bool = False):
        self._handlers: DefaultDict[type, List[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._debug_mode = debug_mode

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        self._handlers[event_type].append(handler)

    def emit(self, event: Any) -> None:
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
            except Exception as e:  # pragma: no cover
                if self._debug_mode:
                    raise
                # best‑effort isolation; logging can be added later
                _ = e
