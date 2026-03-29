"""In-memory game session storage."""

from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.game.economy import EconomicLedger
from agrogame.game.field import FieldManager
from agrogame.game.turn import GameTurnManager, PauseEvent
from agrogame.weather.types import WeatherRecord


@dataclass
class GameSession:
    """One active game in memory."""

    game_id: str
    field_manager: FieldManager
    ledger: EconomicLedger
    turn_manager: GameTurnManager | None = None
    weather: list[WeatherRecord] = field(default_factory=list)
    pause_events: list[PauseEvent] = field(default_factory=list)


# Global in-memory store — no database for V1
games: dict[str, GameSession] = {}
