"""Season state and in-season pause detection (ADR-017, superseding ADR-004).

The simulation engine knows nothing about seasons, pauses or players. This
module reads each simulated day's own stress state and decides when the player
should be told (#470).

``PauseDetector`` subscribes to nothing. Every signal is read from the per-day
event record that each ``Patch`` already keeps (``Patch.recorder``, re-wired on
every crop reset since #402), so detection cannot leak or stack bus handlers
across seasons, crop resets or loads, and cannot change a simulated value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from agrogame.params.phenology import PhenologyStage
from agrogame.plant.events import NutrientStressComputed, WaterStressComputed
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.soil.canopy.runtime import FROST_VULNERABLE_STAGES

if TYPE_CHECKING:
    from agrogame.game.field import Field, Patch
    from agrogame.sim.orchestrator import FullSimulationOrchestrator


class SeasonPhase(Enum):
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    SETTLING = "settling"


class PauseReason(Enum):
    FROST_WARNING = "frost_warning"
    DROUGHT = "drought"
    NUTRIENT_DEFICIENCY = "nutrient_deficiency"


# Stage gates (#470). Drought: a crop is standing between emergence and
# maturity. Nitrogen: the fertiliser response window measured by the #470
# playtest (+12-34% grain through vegetative growth, none from ~15 days into
# grain fill). Frost: exactly the stages the canopy damage model damages.
DROUGHT_STAGES: frozenset[PhenologyStage] = frozenset(
    {
        PhenologyStage.EMERGED,
        PhenologyStage.VEGETATIVE,
        PhenologyStage.FLOWERING,
        PhenologyStage.GRAIN_FILL,
    }
)
N_RESPONSE_STAGES: frozenset[PhenologyStage] = frozenset(
    {PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE, PhenologyStage.FLOWERING}
)
FROST_STAGES: frozenset[PhenologyStage] = FROST_VULNERABLE_STAGES

# Evaluation order on a day. When two interrupting reasons are ready on the same
# day, the earlier one fires and the later one is deferred by the spacing rule.
_REASON_ORDER: tuple[PauseReason, ...] = (
    PauseReason.DROUGHT,
    PauseReason.NUTRIENT_DEFICIENCY,
    PauseReason.FROST_WARNING,
)

# Frost is a notice, not an interrupt: no game action mitigates frost damage
# yet, so promoting it is a separate decision (#470, ADR-017).
_INTERRUPTS: dict[PauseReason, bool] = {
    PauseReason.DROUGHT: True,
    PauseReason.NUTRIENT_DEFICIENCY: True,
    PauseReason.FROST_WARNING: False,
}


@dataclass(frozen=True)
class PauseEvent:
    """One alert raised for a field on a simulated day.

    A plain record rather than a bus event: it is never emitted, and it must
    round-trip through a save unchanged. ``day`` is the 1-based day number of
    the step that raised it, matching ``DailySnapshot.day_number``.
    """

    day: int
    reason: PauseReason
    message: str
    field_id: str = ""
    interrupt: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the save file (optional key within schema v1)."""
        return {
            "day": self.day,
            "reason": self.reason.value,
            "message": self.message,
            "field_id": self.field_id,
            "interrupt": self.interrupt,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PauseEvent:
        """Restore a record written by :meth:`to_dict`."""
        return cls(
            day=int(data["day"]),
            reason=PauseReason(data["reason"]),
            message=str(data.get("message", "")),
            field_id=str(data.get("field_id", "")),
            interrupt=bool(data.get("interrupt", True)),
        )


@dataclass(frozen=True)
class PauseConfig:
    """Game-alert parameters for in-season pauses (#470, ADR-017).

    None of these is a model constant. They decide when the player is told, and
    change no simulated value. Every default is a game-alert parameter
    calibrated by the #470 agent playtest (6 catalog scenarios, seeds 42-51,
    about 600 seasons; table in ADR-017). The rarity target behind them, at
    most 4 interrupts per season, is a judgement rather than a measurement.

    The signals themselves are the simulation's own: Ks is Ta/Tp, the FAO-56
    water-stress coefficient (Allen et al. 1998, eq. 84), as the canopy uses
    it; N stress is the graded NNI-based factor (ADR-013). The frost threshold
    is each crop's own ``frost_threshold_c``.
    """

    drought_ks_threshold: float = 0.4
    drought_onset_days: int = 2
    drought_rearm_days: int = 7
    n_stress_threshold: float = 0.9
    n_onset_days: int = 3
    n_rearm_days: int = 10
    frost_onset_days: int = 1
    frost_rearm_days: int = 7
    # An interrupt never fires within this many days of the previous interrupt
    # on the same field; a suppressed reason is deferred, not dropped.
    interrupt_spacing_days: int = 3

    def __post_init__(self) -> None:
        for name in ("drought_ks_threshold", "n_stress_threshold"):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1], got {value}")
        for name in ("drought_onset_days", "n_onset_days", "frost_onset_days"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1, got {getattr(self, name)}")
        for name in (
            "drought_rearm_days",
            "n_rearm_days",
            "frost_rearm_days",
            "interrupt_spacing_days",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0, got {getattr(self, name)}")

    def onset_days(self, reason: PauseReason) -> int:
        """Consecutive condition days needed before ``reason`` fires."""
        return {
            PauseReason.DROUGHT: self.drought_onset_days,
            PauseReason.NUTRIENT_DEFICIENCY: self.n_onset_days,
            PauseReason.FROST_WARNING: self.frost_onset_days,
        }[reason]

    def rearm_days(self, reason: PauseReason) -> int:
        """Consecutive clear days needed before a fired ``reason`` re-arms."""
        return {
            PauseReason.DROUGHT: self.drought_rearm_days,
            PauseReason.NUTRIENT_DEFICIENCY: self.n_rearm_days,
            PauseReason.FROST_WARNING: self.frost_rearm_days,
        }[reason]


@dataclass(frozen=True)
class PatchDayObservation:
    """What the detector reads from one patch at the end of one day.

    ``water_stress`` and ``n_stress`` are ``None`` when the patch emitted no
    such signal that day (no crop standing).
    """

    crop_key: str
    stage: PhenologyStage
    water_stress: float | None
    n_stress: float | None
    frost_threshold_c: float


def _clamp_unit(value: Any) -> float:
    # Same clamp as CanopyRuntime._on_water_stress / _on_nutrient_stress, so
    # the alert compares exactly the value the canopy acts on.
    return max(0.0, min(1.0, float(value)))


def observe_patch(patch: Patch) -> PatchDayObservation:
    """Read a patch's day from its event record and live crop state.

    Call after the day is stepped and before the recorder is cleared. The last
    emission of each signal wins, as it does for the canopy's own handlers.
    """
    water: float | None = None
    n_stress: float | None = None
    for event in patch.recorder.events:
        if event.event_type == WaterStressComputed.__name__:
            water = _clamp_unit(event.data["stress"])
        elif (
            event.event_type == NutrientStressComputed.__name__
            and str(event.data.get("nutrient", "")).upper() == "N"
        ):
            n_stress = _clamp_unit(event.data["stress"])
    return PatchDayObservation(
        crop_key=patch.config.crop_key,
        stage=patch.orch.phenology.state.stage,
        water_stress=water,
        n_stress=n_stress,
        frost_threshold_c=patch.orch.canopy.params.frost_threshold_c,
    )


@dataclass
class PauseLatchState:
    """Onset/re-arm latch for one (field, reason) pair (#470).

    ``run_days`` counts consecutive days the condition held; ``clear_days``
    counts consecutive days it did not. A fired latch disarms and re-arms after
    ``rearm_days`` clear days. ``deferred`` marks a reason that was ready but
    held back by interrupt spacing; it fires on the first allowed day on which
    its condition still holds.
    """

    armed: bool = True
    run_days: int = 0
    clear_days: int = 0
    deferred: bool = False

    def advance(self, condition: bool, onset_days: int, rearm_days: int) -> bool:
        """Record one day and return whether the reason is ready to fire."""
        if condition:
            self.run_days += 1
            self.clear_days = 0
        else:
            self.run_days = 0
            self.clear_days += 1
            self.deferred = False
        if not self.armed and self.clear_days >= rearm_days:
            self.armed = True
        return self.armed and self.run_days >= onset_days

    def fire(self) -> None:
        """Disarm after the reason has fired."""
        self.armed = False
        self.deferred = False
        self.clear_days = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialise for the save file."""
        return {
            "armed": self.armed,
            "run_days": self.run_days,
            "clear_days": self.clear_days,
            "deferred": self.deferred,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PauseLatchState:
        """Restore a latch, rejecting negative counters."""
        run_days = int(data.get("run_days", 0))
        clear_days = int(data.get("clear_days", 0))
        if run_days < 0 or clear_days < 0:
            raise ValueError(
                f"latch counters must be >= 0, got run={run_days}, clear={clear_days}"
            )
        return cls(
            armed=bool(data.get("armed", True)),
            run_days=run_days,
            clear_days=clear_days,
            deferred=bool(data.get("deferred", False)),
        )


def _standing(obs: PatchDayObservation, stages: frozenset[PhenologyStage]) -> bool:
    return bool(obs.crop_key) and obs.stage in stages


def _low_signals(
    patches: Sequence[PatchDayObservation],
    stages: frozenset[PhenologyStage],
    threshold: float,
    water: bool,
) -> list[float]:
    """Water (Ks) or N stress values below ``threshold`` on gated patches."""
    low: list[float] = []
    for obs in patches:
        value = obs.water_stress if water else obs.n_stress
        if value is not None and value < threshold and _standing(obs, stages):
            low.append(value)
    return low


def _frost_message(
    patches: Sequence[PatchDayObservation], tomorrow_tmin_c: float | None
) -> str:
    """Frost notice text if tomorrow's minimum is below a gated crop's threshold."""
    if tomorrow_tmin_c is None:
        return ""
    frosted = [
        obs
        for obs in patches
        if _standing(obs, FROST_STAGES) and tomorrow_tmin_c < obs.frost_threshold_c
    ]
    if not frosted:
        return ""
    worst = max(frosted, key=lambda obs: obs.frost_threshold_c)
    return (
        f"Frost tomorrow: minimum {tomorrow_tmin_c:.1f} °C, below the "
        f"{worst.crop_key} damage threshold {worst.frost_threshold_c:.1f} °C"
    )


class PauseDetector:
    """Field-level in-season alerts with onset latch and interrupt spacing.

    A field-level condition holds when any of the field's patches meets it,
    because irrigation and fertiliser act field-wide (``execute_action``).
    """

    def __init__(self, config: PauseConfig | None = None) -> None:
        self.config = config or PauseConfig()
        self._latches: dict[tuple[str, PauseReason], PauseLatchState] = {}
        self._last_interrupt_day: dict[str, int] = {}

    def reset(self) -> None:
        """Start a new season: every reason armed, no spacing history."""
        self._latches.clear()
        self._last_interrupt_day.clear()

    def latch(self, field_id: str, reason: PauseReason) -> PauseLatchState:
        """The latch for ``(field_id, reason)``, created armed on first use."""
        key = (field_id, reason)
        if key not in self._latches:
            self._latches[key] = PauseLatchState()
        return self._latches[key]

    def observe_fields(
        self,
        day: int,
        fields: Mapping[str, Field],
        tomorrow_tmin_c: float | None,
    ) -> list[PauseEvent]:
        """Evaluate every field after ``day`` was stepped; return new alerts."""
        fired: list[PauseEvent] = []
        for field_id, fld in fields.items():
            observations = [observe_patch(p) for p in fld.patches]
            fired.extend(
                self.observe_field(field_id, day, observations, tomorrow_tmin_c)
            )
        return fired

    def observe_field(
        self,
        field_id: str,
        day: int,
        patches: Sequence[PatchDayObservation],
        tomorrow_tmin_c: float | None,
    ) -> list[PauseEvent]:
        """Advance one field's latches by one day and return what fired."""
        conditions = self._conditions(patches, tomorrow_tmin_c)
        fired: list[PauseEvent] = []
        for reason in _REASON_ORDER:
            holds, message = conditions[reason]
            latch = self.latch(field_id, reason)
            ready = latch.advance(
                holds, self.config.onset_days(reason), self.config.rearm_days(reason)
            )
            if not ready:
                continue
            interrupt = _INTERRUPTS[reason]
            if interrupt and not self._spacing_allows(field_id, day):
                latch.deferred = True
                continue
            latch.fire()
            if interrupt:
                self._last_interrupt_day[field_id] = day
            fired.append(
                PauseEvent(
                    day=day,
                    reason=reason,
                    message=message,
                    field_id=field_id,
                    interrupt=interrupt,
                )
            )
        return fired

    def _spacing_allows(self, field_id: str, day: int) -> bool:
        last = self._last_interrupt_day.get(field_id)
        return last is None or day - last > self.config.interrupt_spacing_days

    def _conditions(
        self,
        patches: Sequence[PatchDayObservation],
        tomorrow_tmin_c: float | None,
    ) -> dict[PauseReason, tuple[bool, str]]:
        """Today's field-level condition and alert message for each reason."""
        cfg = self.config
        ks = _low_signals(patches, DROUGHT_STAGES, cfg.drought_ks_threshold, water=True)
        n_low = _low_signals(
            patches, N_RESPONSE_STAGES, cfg.n_stress_threshold, water=False
        )
        drought_msg = (
            f"Drought: water stress Ks {min(ks):.2f} below "
            f"{cfg.drought_ks_threshold:.2f}"
            if ks
            else ""
        )
        n_msg = (
            f"Nitrogen deficiency: N stress {min(n_low):.2f} below "
            f"{cfg.n_stress_threshold:.2f}"
            if n_low
            else ""
        )
        frost_msg = _frost_message(patches, tomorrow_tmin_c)
        return {
            PauseReason.DROUGHT: (bool(ks), drought_msg),
            PauseReason.NUTRIENT_DEFICIENCY: (bool(n_low), n_msg),
            PauseReason.FROST_WARNING: (bool(frost_msg), frost_msg),
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialise latch and spacing state (optional key within schema v1)."""
        return {
            "latches": [
                {"field_id": fid, "reason": reason.value, **latch.to_dict()}
                for (fid, reason), latch in self._latches.items()
            ],
            "last_interrupt_day": dict(self._last_interrupt_day),
        }

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], config: PauseConfig | None = None
    ) -> PauseDetector:
        """Restore a detector saved by :meth:`to_dict`."""
        detector = cls(config)
        for entry in data.get("latches", []):
            key = (str(entry["field_id"]), PauseReason(entry["reason"]))
            detector._latches[key] = PauseLatchState.from_dict(entry)
        for fid, day in dict(data.get("last_interrupt_day", {})).items():
            detector._last_interrupt_day[str(fid)] = int(day)
        return detector


def interrupt_count(events: Iterable[PauseEvent]) -> int:
    """Number of interrupting pauses among ``events`` (frost notices excluded)."""
    return sum(1 for event in events if event.interrupt)


@dataclass(frozen=True)
class SeasonResult:
    """Returned at end of season."""

    total_days: int
    grain_g_m2: float
    grain_kg_ha: float
    pause_count: int
    crop_key: str = ""


class GameTurnManager:
    """Season phase, management plan and result for one season (ADR-017).

    Days are stepped by the API's single ``/step`` loop (#487) and alerts are
    raised by :class:`PauseDetector`; this class no longer runs a loop of its
    own, and subscribes to nothing on the orchestrator's bus.
    """

    def __init__(
        self,
        orch: FullSimulationOrchestrator,
        plan: ManagementPlan | None = None,
        crop_key: str = "",
    ) -> None:
        self.orch = orch
        self.plan = plan or ManagementPlan()
        self.orch.management_plan = self.plan
        self.crop_key = crop_key

        self.phase = SeasonPhase.PLANNING
        self.current_day: int = 0
        self.result: SeasonResult | None = None

    def close(self) -> None:
        """Retire this manager when the session replaces it (#486).

        Since #470 the manager holds no bus subscription (pause detection reads
        each patch's day record instead), so there is nothing left to release.
        Kept so every replacement still goes through one retirement point.
        """

    def revise_plan(self, from_day: int, new_events: list[ManagementEvent]) -> None:
        """Revise the management plan from a given day onward."""
        self.plan.revise(from_day, new_events)

    def to_dict(self) -> dict[str, Any]:
        """Serialise phase, day, crop and plan."""
        return {
            "current_day": self.current_day,
            "phase": self.phase.value,
            "crop_key": self.crop_key,
            "plan": self.plan.to_dict(),
        }

    @classmethod
    def restore_state(
        cls, data: dict[str, Any], orch: FullSimulationOrchestrator
    ) -> GameTurnManager:
        """Restore a mid-season GameTurnManager from saved state."""
        plan = ManagementPlan.from_dict(data.get("plan", {"events": []}))
        mgr = cls(orch=orch, plan=plan, crop_key=data.get("crop_key", ""))
        mgr.current_day = int(data["current_day"])
        mgr.phase = SeasonPhase(data["phase"])
        return mgr
