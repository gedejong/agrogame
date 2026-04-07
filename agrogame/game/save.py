"""Game state persistence — save/load to JSON files (ADR-001, AGRO-36).

Provides GameState dataclass wrapping all serializable state, with
checksum verification and atomic file writes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import agrogame

from agrogame.game.economy import EconomicLedger
from agrogame.game.field import FieldManager

SCHEMA_VERSION = 1


@dataclass
class GameState:
    """Top-level save wrapper combining all game subsystem states."""

    game_id: str
    field_manager_data: dict[str, Any]
    ledger_data: dict[str, Any]
    weather_data: list[dict[str, Any]]
    current_date: str  # ISO format
    base_seed: int
    run_count: int
    day_index: int
    season_days: int
    season_active: bool = False
    season_settled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON persistence."""
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "engine_version": getattr(agrogame, "__version__", "0.0.0"),
            "game_id": self.game_id,
            "field_manager": self.field_manager_data,
            "ledger": self.ledger_data,
            "current_date": self.current_date,
            "base_seed": self.base_seed,
            "run_count": self.run_count,
            "day_index": self.day_index,
            "season_days": self.season_days,
            "season_active": self.season_active,
            "season_settled": self.season_settled,
            "weather": self.weather_data,
        }
        payload["checksum"] = _compute_checksum(payload)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameState:
        """Restore from a plain dict, validating checksum and version."""
        version = data.get("schema_version")
        if version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported save version {version} (expected {SCHEMA_VERSION})"
            )
        stored_checksum = data.get("checksum", "")
        verify_data = {k: v for k, v in data.items() if k != "checksum"}
        expected = _compute_checksum(verify_data)
        if stored_checksum != expected:
            raise ValueError("Save file integrity check failed: checksum mismatch")
        return cls(
            game_id=str(data["game_id"]),
            field_manager_data=data["field_manager"],
            ledger_data=data["ledger"],
            current_date=str(data["current_date"]),
            base_seed=int(data.get("base_seed", 42)),
            run_count=int(data.get("run_count", 0)),
            day_index=int(data.get("day_index", 0)),
            season_days=int(data.get("season_days", 200)),
            season_active=bool(data.get("season_active", False)),
            season_settled=bool(data.get("season_settled", False)),
            weather_data=data.get("weather", []),
        )

    def to_session_kwargs(self) -> dict[str, Any]:
        """Build kwargs for reconstructing a GameSession from this state."""
        from agrogame.weather.types import WeatherRecord

        weather = [WeatherRecord.from_dict(w) for w in self.weather_data]
        return {
            "game_id": self.game_id,
            "field_manager": FieldManager.from_dict(self.field_manager_data),
            "ledger": EconomicLedger.from_dict(self.ledger_data),
            "weather": weather,
            "current_date": date.fromisoformat(self.current_date),
            "base_seed": self.base_seed,
            "run_count": self.run_count,
            "day_index": self.day_index,
            "season_days": self.season_days,
            "season_active": self.season_active,
            "season_settled": self.season_settled,
        }


def _compute_checksum(data: dict[str, Any]) -> str:
    """SHA-256 hex digest of deterministic JSON encoding."""
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def save_to_file(state: GameState, path: Path) -> Path:
    """Atomic write: serialize to .tmp, then os.replace() to target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    payload = state.to_dict()
    raw = json.dumps(payload, indent=2, default=str)
    tmp_path.write_text(raw, encoding="utf-8")
    os.replace(str(tmp_path), str(path))
    return path


def load_from_file(path: Path) -> GameState:
    """Load and validate a save file."""
    if not path.exists():
        raise FileNotFoundError(f"Save file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return GameState.from_dict(data)
