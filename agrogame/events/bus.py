"""Synchronous in-process event bus used by every simulation module."""

from __future__ import annotations

import logging
from typing import Any, TypeVar
from collections.abc import Callable
from collections import defaultdict


logger = logging.getLogger(__name__)
T = TypeVar("T")


class EventBus:
    """Synchronous event dispatcher with debug logging and error isolation."""

    def __init__(self, debug_mode: bool = False):
        """Create a new bus. Pass debug_mode=True to re-raise handler errors."""
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._debug_mode = debug_mode

    def subscribe(self, event_type: type[T], handler: Callable[[T], None]) -> None:
        """Register `handler` to be called every time an `event_type` is emitted."""
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: type[T], handler: Callable[[T], None]) -> bool:
        """Remove one registration of `handler` for `event_type` (#486).

        Teardown path for an **external observer that is retired while the bus
        lives on**, such as a `GameTurnManager` replaced at season setup: the
        observer removes exactly its own subscription. Contrast `clear()`.

        Bound methods compare equal when they wrap the same function on the
        same instance, so the method passed to `subscribe` can be removed with
        a fresh reference to it. Returns True if a registration was removed and
        False if none was present (e.g. the bus was cleared since).
        """
        handlers = self._handlers.get(event_type)
        if not handlers or handler not in handlers:
            return False
        handlers.remove(handler)
        return True

    def clear(self) -> None:
        """Remove all event subscriptions.

        Teardown path for the **whole bus**, used when its owner rebuilds every
        subscription itself (the orchestrator's crop reset re-wires its own
        modules). Never use it to retire a single observer: it would drop the
        simulation's subscriptions too. Use `unsubscribe()` for that.
        """
        self._handlers.clear()

    def emit(self, event: Any) -> None:
        """Dispatch `event` to exact-type subscribers and BaseEvent catch-alls."""
        # Debug log every emitted event for traceability
        try:
            payload = getattr(event, "to_dict", lambda: {"event": str(event)})()
        except Exception:
            payload = {"event": str(event)}
        logger.debug("event_bus.emit", extra={"event": payload})

        # Deliver to exact-type subscribers
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
            except Exception as e:  # pragma: no cover
                if self._debug_mode:
                    raise
                # best-effort isolation; log exception at debug level
                logger.debug("event_handler_exception", exc_info=e)
        # Also deliver to BaseEvent subscribers (catch-all)
        from .base import BaseEvent  # local import to avoid cycles

        if isinstance(event, BaseEvent):
            for handler in list(self._handlers[BaseEvent]):
                try:
                    handler(event)
                except Exception as e:  # pragma: no cover
                    if self._debug_mode:
                        raise
                    logger.debug("event_handler_exception", exc_info=e)
