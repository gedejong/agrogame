"""Deprecated shim for EventBus location.

Import `EventBus` from `agrogame.events` instead. This module remains to
preserve backward compatibility and will be removed in a later release.
"""

from __future__ import annotations

from agrogame.events import EventBus  # noqa: F401
