"""Synchronous in-process event bus used by every simulation module."""

from __future__ import annotations

import logging
from typing import Any, TypeVar
from collections.abc import Callable
from collections import defaultdict


logger = logging.getLogger(__name__)
T = TypeVar("T")


class EventHandlerError(RuntimeError):
    """A subscribed handler raised while the bus dispatched an event (#606).

    ``handler`` is the handler's ``module.qualname`` (its ``repr`` when it has
    none) and ``event_type`` the event's class name. The handler's own
    exception is the ``__cause__``. ``str(exc)`` names the handler, the
    exception class and the event type but not the exception's message, so it
    is safe to return to an API client; the chained traceback carries the rest.
    """

    def __init__(self, handler: str, event_type: str, cause: Exception) -> None:
        """Record which handler failed on which event, and how."""
        super().__init__(
            f"{handler} raised {type(cause).__name__} while handling {event_type}"
        )
        self.handler = handler
        self.event_type = event_type


def _handler_name(handler: Callable[[Any], None]) -> str:
    """``module.qualname`` of a function or bound method, else its ``repr``."""
    module = getattr(handler, "__module__", None)
    qualname = getattr(handler, "__qualname__", None)
    if isinstance(module, str) and isinstance(qualname, str):
        return f"{module}.{qualname}"
    return repr(handler)


def _deliver(handlers: list[Callable[[Any], None]], event: Any) -> None:
    """Call each handler in order; the first exception stops delivery (#606).

    An ``EventHandlerError`` from a nested ``emit`` passes through unchanged,
    so the error names the innermost handler that actually raised. Any other
    exception is wrapped in ``EventHandlerError`` and chained from the original.
    """
    for handler in handlers:
        try:
            handler(event)
        except EventHandlerError:
            raise
        except Exception as exc:
            raise EventHandlerError(
                _handler_name(handler), type(event).__name__, exc
            ) from exc


class EventBus:
    """Synchronous event dispatcher with debug logging.

    Handler exceptions are not isolated: every one propagates out of `emit` as
    `EventHandlerError` (#606, docs/events.md "Handler exceptions").
    """

    def __init__(self) -> None:
        """Create a new bus with no subscriptions."""
        self._handlers: defaultdict[type, list[Callable[[Any], None]]] = defaultdict(
            list
        )

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
        """Dispatch `event` to exact-type subscribers, then BaseEvent catch-alls.

        Raises:
            EventHandlerError: a handler raised. Handlers after it, including
                every catch-all when an exact-type handler failed, are not
                called.
        """
        # Debug log every emitted event for traceability. A payload that cannot
        # be built is a logging problem, not a handler failure: log its str.
        try:
            payload = getattr(event, "to_dict", lambda: {"event": str(event)})()
        except Exception:
            payload = {"event": str(event)}
        logger.debug("event_bus.emit", extra={"event": payload})

        _deliver(list(self._handlers[type(event)]), event)
        from .base import BaseEvent  # local import to avoid cycles

        if isinstance(event, BaseEvent):
            _deliver(list(self._handlers[BaseEvent]), event)
