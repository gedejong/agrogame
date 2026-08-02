"""Snapshot of the microbes module `event_type` strings (issue #283, AC6).

`BaseEvent.to_dict` derives `event_type` from ``type(self).__name__``, so the
serialized string is exactly the class name. Freezing the full set guards
against accidental renames: any change to this set must be intentional and
reviewed. State-change events use past-tense naming; ``*Computed`` is reserved
for non-mutating diagnostics.
"""

from __future__ import annotations

import inspect

from agrogame.events import BaseEvent
from agrogame.soil.microbes import events as microbes_events

# Frozen snapshot of every event_type defined by the microbes module.
EXPECTED_MICROBES_EVENT_TYPES = {
    # State-change events (past-tense)
    "MicrobialGrowthOccurred",
    "MicrobialMortalityOccurred",
    "EnzymeProduced",
    "MicrobialFBUpdated",
    "SubstrateReleased",
    "RhizospherePrimingOccurred",
    # Diagnostics (non-mutating; *Computed or explicit snapshot)
    "MicrobialActivityComputed",
    "EnzymeGroupTotalsComputed",
    "MicrobialSnapshot",
}


def _microbes_event_type_strings() -> set[str]:
    names: set[str] = set()
    for _name, obj in inspect.getmembers(microbes_events, inspect.isclass):
        if (
            issubclass(obj, BaseEvent)
            and obj is not BaseEvent
            and obj.__module__ == microbes_events.__name__
        ):
            names.add(obj.__name__)
    return names


def test_microbes_event_type_strings_match_snapshot() -> None:
    assert _microbes_event_type_strings() == EXPECTED_MICROBES_EVENT_TYPES


def test_no_present_tense_state_change_names() -> None:
    # The renamed present-tense state-change classes must not reappear.
    forbidden = {
        "MicrobialGrowth",
        "MicrobialMortality",
        "SubstrateAvailable",
        "RhizospherePrimingPulse",
        "EnzymeGroupTotals",
    }
    assert forbidden.isdisjoint(_microbes_event_type_strings())
