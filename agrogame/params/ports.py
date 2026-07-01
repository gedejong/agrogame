"""Structural Protocol ports shared across the simulation engine.

A *port* is a structural (`typing.Protocol`) view of a concrete value object
that a runtime or module reads but does not own. Runtimes take ports rather
than concrete Pydantic models so that (a) any object with the right shape can
be passed in tests without building a YAML-validated preset, and (b) the
soil/plant/atmosphere domains couple to a structural shape instead of to
``agrogame.soil.models`` directly.

This module lives under ``agrogame.params`` because it is a cross-cutting,
dependency-free leaf: it imports only stdlib typing. See ADR-008 (Protocol
port doctrine) for when to define a port versus take a concrete type.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# ET ports (relocated from agrogame/atmosphere/et/ports.py, #310)
# ---------------------------------------------------------------------------


class SoilLayer(Protocol):
    """Minimal layer interface needed by ET for topsoil evaporation.

    Concrete soil layer objects should provide these attributes.
    """

    wilting_point: float
    depth_cm: float


@runtime_checkable
class WaterProfile(Protocol):
    """Abstraction of a soil/water profile for ET extraction.

    ``layers`` is a read-only property so the member is covariant: a
    concrete profile whose layers are a subtype of ``SoilLayer`` (e.g. the
    Pydantic ``SoilProfile``, or the broader ``SoilProfileView`` below)
    satisfies this protocol without a cast.
    """

    @property
    def layers(self) -> Sequence[SoilLayer]: ...


@runtime_checkable
class WaterState(Protocol):
    """Abstraction of soil water state read by ET and the N/P cycles.

    ``theta`` (volumetric water content per layer) is read by the nitrogen
    and phosphorus cycles; the ``*_storage_mm`` methods are used by ET for
    transpiration/evaporation bookkeeping.
    """

    @property
    def theta(self) -> Sequence[float]: ...

    def layer_storage_mm(self, profile: WaterProfile, _layer_index: int) -> float: ...

    def set_layer_storage_mm(
        self, profile: SoilProfileView, _layer_index: int, _storage_mm: float
    ) -> None: ...


@runtime_checkable
class TranspirationExtractor(Protocol):
    """Capability to extract transpiration by root distribution.

    Implemented by water models.
    """

    def extract_transpiration_by_roots(
        self,
        profile: WaterProfile,
        state: WaterState,
        _transpiration_mm: float,
        root_fractions: Sequence[float],
    ) -> float: ...


@runtime_checkable
class EvaporationApplier(Protocol):
    """Capability to apply evaporation removal from topsoil."""

    def apply_evaporation(
        self, profile: WaterProfile, state: WaterState, evaporation_mm: float
    ) -> float: ...


@runtime_checkable
class WaterActuator(TranspirationExtractor, Protocol):
    """Composite protocol for water actions used by ET."""

    def apply_evaporation(
        self, profile: WaterProfile, state: WaterState, evaporation_mm: float
    ) -> float: ...


@runtime_checkable
class RootDistribution(Protocol):
    """Per-layer root fractions, used to partition transpiration uptake."""

    layer_fractions: Sequence[float] | None


class _CanopyStateLike(Protocol):
    lai: float


@runtime_checkable
class CanopyView(Protocol):
    """Read-only view of canopy state needed by ET (just ``state.lai``)."""

    state: _CanopyStateLike


# ---------------------------------------------------------------------------
# Soil-profile ports (new in #310)
# ---------------------------------------------------------------------------


@runtime_checkable
class SoilLayerView(SoilLayer, Protocol):
    """Structural view of a single soil layer read by soil/plant runtimes.

    Extends the ET ``SoilLayer`` (``wilting_point`` + ``depth_cm``) with the
    union of attributes the migrated runtimes and the module methods they
    forward to access. The concrete ``agrogame.soil.models.SoilLayer``
    satisfies this shape; so does any duck-typed fake used in tests (e.g.
    ``types.SimpleNamespace``).
    """

    saturation: float
    field_capacity: float
    bulk_density_g_cm3: float
    ksat_mm_per_hour: float
    organic_matter_pct: float
    clay_pct: float | None
    initial_no3_kg_ha: float
    initial_nh4_kg_ha: float
    initial_p_kg_ha: float

    # Read-only (covariant) so the concrete ``Literal[...]`` texture on
    # ``SoilProfile`` satisfies this without importing the soil enum — which
    # would break the ``agrogame.params`` leaf boundary.
    @property
    def texture(self) -> str: ...


@runtime_checkable
class SoilProfileView(WaterProfile, Protocol):
    """Structural view of a soil profile read by soil/plant runtimes.

    The read-only counterpart to ``agrogame.soil.models.SoilProfile`` that
    runtimes take at construction so they never couple to the concrete
    Pydantic model. Extends ``WaterProfile`` (covariant ``layers`` property)
    so a ``SoilProfileView`` is also accepted anywhere a ``WaterProfile`` is
    expected — e.g. ``WaterState.layer_storage_mm``.
    """

    name: str

    @property
    def layers(self) -> Sequence[SoilLayerView]: ...
