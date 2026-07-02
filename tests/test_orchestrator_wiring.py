"""Wiring-order regression tests for ``FullSimulationOrchestrator`` (#323).

These guard the order-critical event-subscription DAG (ADR-010). The bus
dispatches handlers in subscription order, so the refactor that decomposed
``__init__`` / ``_wire_runtimes`` into factories + an explicit subscription
plan is behaviour-neutral **iff** the emitted per-event handler order is
identical to the pre-refactor baseline — for both the fresh ``__init__`` build
and the post-``reset_crop`` build. The golden fixture
(``tests/fixtures/wiring_order_golden.json``) was captured from pre-refactor
``main``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets

_GOLDEN = Path(__file__).parent / "fixtures" / "wiring_order_golden.json"
# DayTick handlers that must run *after* the pore chain on ``day_start``
# because they consume the refreshed pore/gas geometry (ADR-010).
_PORE_CHAIN_HANDLERS = (
    "PoreNetworkRuntime._on_day_tick",
    "BioporesRuntime._on_day_tick",
    "GasDiffusionRuntime._on_day_tick",
)
_PORE_CHAIN_CONSUMERS = (
    "WaterRuntime._on_day_tick",
    "RedoxRuntime._on_day_tick",
    "NitrogenRuntime._on_day_tick",
)


def _handler_id(handler: object) -> str:
    slf = getattr(handler, "__self__", None)
    cls = type(slf).__name__ if slf is not None else "<func>"
    return f"{cls}.{getattr(handler, '__name__', repr(handler))}"


def _subscription_order(orch: FullSimulationOrchestrator) -> dict[str, list[str]]:
    """Per-event-type handler order, dropping benign empty entries."""
    out: dict[str, list[str]] = {}
    for etype, handlers in orch.event_bus._handlers.items():
        ids = [_handler_id(h) for h in handlers]
        if ids:
            out[etype.__name__] = ids
    return out


def _build_orchestrator() -> FullSimulationOrchestrator:
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    return FullSimulationOrchestrator(profile)


@pytest.fixture(scope="module")
def golden() -> dict[str, list[str]]:
    return json.loads(_GOLDEN.read_text())


def test_wiring_order_matches_golden(golden: dict[str, list[str]]) -> None:
    """Fresh ``__init__`` reproduces the pre-refactor subscription order."""
    orch = _build_orchestrator()
    assert _subscription_order(orch) == golden


def test_reset_crop_preserves_wiring_order(golden: dict[str, list[str]]) -> None:
    """``reset_crop`` produces the same subscription order as ``__init__``.

    The reset path is where the pre-refactor construction diverged (it
    rebuilt only a subset of modules); the shared-factory refactor must make
    the two paths' wiring identical — and identical to the golden.
    """
    orch = _build_orchestrator()
    before = _subscription_order(orch)

    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch.reset_crop(crops.get_preset("winter_wheat"))
    after = _subscription_order(orch)

    assert after == before
    assert after == golden


def test_reset_crop_twice_stable(golden: dict[str, list[str]]) -> None:
    """Wiring order is stable across ≥2 ``reset_crop`` cycles."""
    orch = _build_orchestrator()
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    orch.reset_crop(crops.get_preset("maize"))
    orch.reset_crop(crops.get_preset("winter_wheat"))
    assert _subscription_order(orch) == golden


def test_pore_chain_dispatches_before_consumers() -> None:
    """On ``DayTick``, pore-chain handlers precede water/redox/N (ADR-010)."""
    orch = _build_orchestrator()
    order = _subscription_order(orch)["DayTick"]
    positions = {name: order.index(name) for name in order}
    last_pore = max(positions[h] for h in _PORE_CHAIN_HANDLERS)
    first_consumer = min(positions[c] for c in _PORE_CHAIN_CONSUMERS)
    assert last_pore < first_consumer, (
        "ADR-010 violation: a pore-chain runtime dispatches after a "
        f"consumer. DayTick order: {order}"
    )


def test_subscription_plan_group_order() -> None:
    """The plan lists the pore-chain group before the core group."""
    orch = _build_orchestrator()
    plan = orch._subscription_plan()
    group_order = [name for name, _ in plan]
    assert group_order == [
        FullSimulationOrchestrator._PORE_CHAIN_GROUP,
        FullSimulationOrchestrator._CORE_GROUP,
        FullSimulationOrchestrator._BOOKKEEPING_GROUP,
    ]


def test_pore_chain_first_invariant_enforced_in_code() -> None:
    """``_assert_pore_chain_registered_first`` rejects a reordered plan.

    This is the code-level guard for the ADR-010 invariant: a plan that puts
    core runtimes before the pore chain must raise, turning a silent
    coupling break into a construction-time error.
    """
    ok_plan = [
        (FullSimulationOrchestrator._PORE_CHAIN_GROUP, []),
        (FullSimulationOrchestrator._CORE_GROUP, []),
    ]
    # Well-ordered plan: no raise.
    FullSimulationOrchestrator._assert_pore_chain_registered_first(ok_plan)

    bad_plan = [
        (FullSimulationOrchestrator._CORE_GROUP, []),
        (FullSimulationOrchestrator._PORE_CHAIN_GROUP, []),
    ]
    with pytest.raises(ValueError, match="ADR-010 violation"):
        FullSimulationOrchestrator._assert_pore_chain_registered_first(bad_plan)


def test_subscription_plan_missing_groups_raise() -> None:
    """A plan missing a required group is rejected."""
    with pytest.raises(ValueError, match="missing the pore-chain group"):
        FullSimulationOrchestrator._assert_pore_chain_registered_first(
            [(FullSimulationOrchestrator._CORE_GROUP, [])]
        )
    with pytest.raises(ValueError, match="missing the core group"):
        FullSimulationOrchestrator._assert_pore_chain_registered_first(
            [(FullSimulationOrchestrator._PORE_CHAIN_GROUP, [])]
        )
