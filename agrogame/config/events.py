from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from agrogame.events.base import BaseEvent


@dataclass(frozen=True)
class ConfigReloaded(BaseEvent):
    """Emitted when configuration files are reloaded successfully."""

    files: List[Path]
    schema: str
