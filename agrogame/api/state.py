"""In-memory game session storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agrogame.game.economy import EconomicLedger
from agrogame.game.field import FieldManager
from agrogame.game.turn import GameTurnManager, PauseDetector, PauseEvent
from agrogame.weather.types import WeatherRecord

# Default simulation start date (Northern hemisphere spring).
DEFAULT_START_DATE = date(2024, 4, 1)

# Default season length in days.
DEFAULT_SEASON_DAYS = 200


@dataclass
class GameSession:
    """One active game in memory."""

    game_id: str
    field_manager: FieldManager
    ledger: EconomicLedger
    turn_manager: GameTurnManager | None = None
    weather: list[WeatherRecord] = field(default_factory=list)
    # This season's alerts, interrupting and not (#470).
    pause_events: list[PauseEvent] = field(default_factory=list)
    # In-season alert detector run by /step (#470). ``None`` disables detection;
    # that is a control for tests, not a player setting, and is not saved.
    pause_detector: PauseDetector | None = field(default_factory=PauseDetector)
    current_date: date = DEFAULT_START_DATE
    base_seed: int = 42
    run_count: int = 0
    day_index: int = 0
    season_days: int = DEFAULT_SEASON_DAYS
    season_active: bool = False
    season_settled: bool = False
    # The /step that completed this season has run: standing crops are settled
    # and completion cannot happen again until the next season starts (#518).
    season_completed: bool = False


# Global in-memory store — no database for V1
games: dict[str, GameSession] = {}
