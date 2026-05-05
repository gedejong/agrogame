from __future__ import annotations

from pathlib import Path
from typing import Any
from collections.abc import Callable, Iterable

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer as WatchdogObserver


class _Handler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[list[Path]], None], exts: set[str]):
        super().__init__()
        self._on_change = on_change
        self._exts = exts

    def on_any_event(self, event: Any) -> None:  # pragma: no cover - thin wrapper
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in self._exts:
            self._on_change([p])


def watch(paths: Iterable[Path], on_change: Callable[[list[Path]], None]) -> Any:
    """Watch paths for YAML/JSON changes and call on_change with changed files.

    Caller is responsible for stopping the observer.
    """
    observer = WatchdogObserver()
    handler = _Handler(on_change, {".yml", ".yaml", ".json"})
    for p in paths:
        observer.schedule(handler, str(p), recursive=True)
    observer.start()
    return observer
