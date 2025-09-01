from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, List

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


class _Handler(FileSystemEventHandler):
    def __init__(self, on_change: Callable[[List[Path]], None], exts: set[str]):
        super().__init__()
        self._on_change = on_change
        self._exts = exts

    def on_any_event(self, event):  # type: ignore[override]
        if event.is_directory:
            return
        p = Path(event.src_path)
        if p.suffix.lower() in self._exts:
            self._on_change([p])


def watch(paths: Iterable[Path], on_change: Callable[[List[Path]], None]) -> Observer:
    """Watch paths for YAML/JSON changes and call on_change with changed files.

    Caller is responsible for stopping the observer.
    """
    observer = Observer()
    handler = _Handler(on_change, {".yml", ".yaml", ".json"})
    for p in paths:
        observer.schedule(handler, str(p), recursive=True)
    observer.start()
    return observer
