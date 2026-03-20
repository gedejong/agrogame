from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass(frozen=True)
class BaseEvent:
    """Base class for domain events with utility helpers.

    Provides timestamp and to_dict for logging/visualization. Subclasses can
    add fields freely; `to_dict` will serialize dataclass fields.
    """

    # Not part of __init__ to avoid ordering constraints in subclasses
    timestamp: datetime = field(default_factory=datetime.utcnow, init=False)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Ensure timestamp is ISO string for logging/JSON
        ts = data.get("timestamp")
        if isinstance(ts, datetime):
            data["timestamp"] = ts.isoformat()
        data["event_type"] = type(self).__name__
        return data
