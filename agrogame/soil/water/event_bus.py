"""Lightweight synchronous event bus for water module.

This module defines a minimal, synchronous event bus used by the water
subsystem to emit and subscribe to domain events without introducing
cross-module dependencies or asynchronous complexity.
"""

from __future__ import annotations

from typing import Any, Callable, DefaultDict, List, Type, TypeVar
from collections import defaultdict


T = TypeVar("T")


class EventBus:
    """Synchronous event dispatcher with best-effort error isolation.

    The bus preserves registration order and executes handlers synchronously
    in-process. Handlers run in a try/except guard; if ``debug_mode`` is True,
    exceptions are re-raised to aid debugging.

    Args:
        debug_mode: When True, re-raise handler exceptions.
    """

    def __init__(self, debug_mode: bool = False):
        """Initialize the event bus.

        Args:
            debug_mode: When True, re-raise handler exceptions.
        """
        self._handlers: DefaultDict[type, List[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._debug_mode = debug_mode

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Register a handler for a specific event type.

        Args:
            event_type: The event class to subscribe to.
            handler: Callable invoked with the event instance.
        """
        self._handlers[event_type].append(handler)

    def emit(self, event: Any) -> None:
        """Emit an event instance to all subscribers of its type.

        Args:
            event: The event instance to publish.
        """
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
            except Exception as e:  # pragma: no cover
                if self._debug_mode:
                    raise
                # best-effort isolation; logging can be added later
                _ = e
