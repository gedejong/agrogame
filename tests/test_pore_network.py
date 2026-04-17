"""Tests for pore network module (#211).

Validates pore size distribution derived from texture and aggregation
state via retention-curve PTFs (Rawls et al. 1982/1983).
"""

from __future__ import annotations

import pytest

from agrogame.events import EventBus
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import (
    SoilLayer,
    SoilProfile,
    TEXTURE_TO_SAND,
    TEXTURE_TO_SILT,
)
from agrogame.soil.pore_network import (
    PoreNetworkComputed,
    PoreNetworkModule,
    PoreNetworkParams,
    PoreNetworkState,
)

# ---------- helpers ----------

# Representative soil profiles for each texture class.
# Values from Rawls et al. 1982 Table 2 (class averages).
TEXTURE_PROFILES: dict[str, dict[str, float]] = {
    "sand": {
        "saturation": 0.395,
        "field_capacity": 0.12,
        "wilting_point": 0.06,
        "bulk_density": 1.60,
        "om_pct": 0.5,
    },
    "sandy_loam": {
        "saturation": 0.453,
        "field_capacity": 0.21,
        "wilting_point": 0.10,
        "bulk_density": 1.45,
        "om_pct": 1.5,
    },
    "loam": {
        "saturation": 0.501,
        "field_capacity": 0.27,
        "wilting_point": 0.12,
        "bulk_density": 1.35,
        "om_pct": 2.5,
    },
    "clay_loam": {
        "saturation": 0.501,
        "field_capacity": 0.32,
        "wilting_point": 0.19,
        "bulk_density": 1.30,
        "om_pct": 2.5,
    },
    "clay": {
        "saturation": 0.575,
        "field_capacity": 0.40,
        "wilting_point": 0.27,
        "bulk_density": 1.15,
        "om_pct": 3.0,
    },
}


def _make_profile(texture: str) -> SoilProfile:
    """Build a 3-layer profile with given texture."""
    vals = TEXTURE_PROFILES[texture]
    layer = SoilLayer(
        depth_cm=40.0,
        texture=texture,
        field_capacity=vals["field_capacity"],
        wilting_point=vals["wilting_point"],
        saturation=vals["saturation"],
        bulk_density_g_cm3=vals["bulk_density"],
        ksat_mm_per_hour=25.0,
        organic_matter_pct=vals["om_pct"],
        initial_no3_kg_ha=20.0,
        initial_nh4_kg_ha=5.0,
        initial_p_kg_ha=10.0,
    )
    return SoilProfile(name=f"test_{texture}", layers=[layer, layer, layer])


# ---------- AC: PoreNetworkState dataclass ----------


def test_state_empty() -> None:
    state = PoreNetworkState.empty(3)
    assert len(state.macro) == 3
    assert all(v == 0.0 for v in state.macro)


def test_state_total_porosity() -> None:
    state = PoreNetworkState(
        macro=[0.10], meso=[0.15], micro=[0.12], crypto=[0.08], connectivity=[0.2]
    )
    assert abs(state.total_porosity(0) - 0.45) < 1e-9


def test_state_round_trip() -> None:
    state = PoreNetworkState(
        macro=[0.10, 0.08],
        meso=[0.15, 0.14],
        micro=[0.12, 0.13],
        crypto=[0.08, 0.10],
        connectivity=[0.22, 0.18],
    )
    d = state.to_dict()
    restored = PoreNetworkState.from_dict(d)
    assert restored.macro == state.macro
    assert restored.crypto == state.crypto
    assert restored.connectivity == state.connectivity


# ---------- AC: PoreNetworkParams frozen ----------


def test_params_frozen() -> None:
    p = PoreNetworkParams()
    with pytest.raises(AttributeError):
        p.mwd_baseline = 99.0  # type: ignore[misc]


# ---------- AC: TEXTURE_TO_SAND / TEXTURE_TO_SILT ----------


def test_texture_sand_silt_defined() -> None:
    for tex in ["sand", "sandy_loam", "loam", "clay_loam", "clay", "peat"]:
        assert tex in TEXTURE_TO_SAND, f"Missing sand for {tex}"
        assert tex in TEXTURE_TO_SILT, f"Missing silt for {tex}"


def test_texture_sand_silt_clay_sum_reasonable() -> None:
    """Sand + silt + clay should be ~100% for mineral soils."""
    from agrogame.soil.models import TEXTURE_TO_CLAY

    for tex in ["sand", "sandy_loam", "loam", "clay_loam", "clay"]:
        total = TEXTURE_TO_SAND[tex] + TEXTURE_TO_SILT[tex] + TEXTURE_TO_CLAY[tex]
        assert 95.0 <= total <= 105.0, f"{tex}: sand+silt+clay = {total}"


# ---------- AC: Pore fractions from texture via PTF ----------


@pytest.mark.parametrize(
    "texture,expected_macro_lo,expected_macro_hi,expected_micro_lo,expected_micro_hi",
    [
        # Ref: Rawls et al. 1982 Table 2; Lal & Shukla 2004 Ch. 5.
        # "micro" range is narrower than literature "micropore" because
        # our 4-class system separates cryptopores (<0.2 um) from
        # micropores (0.2-10 um). Literature lumps both.
        ("sand", 0.15, 0.30, 0.00, 0.10),
        ("sandy_loam", 0.10, 0.28, 0.02, 0.15),
        ("loam", 0.05, 0.25, 0.03, 0.20),
        ("clay_loam", 0.03, 0.20, 0.05, 0.25),
        ("clay", 0.02, 0.20, 0.10, 0.35),
    ],
)
def test_texture_pore_distribution(
    texture: str,
    expected_macro_lo: float,
    expected_macro_hi: float,
    expected_micro_lo: float,
    expected_micro_hi: float,
) -> None:
    profile = _make_profile(texture)
    state = PoreNetworkState.empty(3)
    module = PoreNetworkModule(PoreNetworkParams(), state)
    module.compute(profile)

    macro = state.macro[0]
    micro = state.micro[0]
    assert (
        expected_macro_lo <= macro <= expected_macro_hi
    ), f"{texture}: macro={macro:.3f} not in [{expected_macro_lo}, {expected_macro_hi}]"
    assert (
        expected_micro_lo <= micro <= expected_micro_hi
    ), f"{texture}: micro={micro:.3f} not in [{expected_micro_lo}, {expected_micro_hi}]"


# ---------- AC: Total porosity constraint ----------


@pytest.mark.parametrize("texture", ["sand", "sandy_loam", "loam", "clay_loam", "clay"])
def test_porosity_sum_equals_saturation(texture: str) -> None:
    """Macro + meso + micro + crypto must equal layer saturation."""
    profile = _make_profile(texture)
    state = PoreNetworkState.empty(3)
    module = PoreNetworkModule(PoreNetworkParams(), state)
    module.compute(profile)

    for i in range(3):
        total = state.total_porosity(i)
        expected = profile.layers[i].saturation
        assert (
            abs(total - expected) < 1e-6
        ), f"Layer {i}: total porosity {total:.6f} != saturation {expected:.6f}"


# ---------- AC: Connectivity in [0, 1] ----------


@pytest.mark.parametrize("texture", ["sand", "sandy_loam", "loam", "clay_loam", "clay"])
def test_connectivity_range(texture: str) -> None:
    profile = _make_profile(texture)
    state = PoreNetworkState.empty(3)
    module = PoreNetworkModule(PoreNetworkParams(), state)
    module.compute(profile)

    for i in range(3):
        c = state.connectivity[i]
        assert 0.0 <= c <= 1.0, f"Layer {i}: connectivity {c} out of [0, 1]"


# ---------- AC: Aggregation MWD increases macroporosity ----------


def test_high_mwd_increases_macroporosity() -> None:
    """Well-aggregated soil (high MWD) should have more macropores than
    degraded soil (low MWD).
    Ref: Dexter 2004, Geoderma — macroporosity scales with aggregation.
    """
    profile = _make_profile("loam")
    n = len(profile.layers)

    # Low MWD scenario (degraded: mostly microaggregates)
    agg_low = SoilAggregationState(micro=[0.80] * n, meso=[0.15] * n, macro=[0.05] * n)
    state_low = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), state_low).compute(profile, agg_low)

    # High MWD scenario (well-aggregated: many macroaggregates)
    agg_high = SoilAggregationState(micro=[0.15] * n, meso=[0.25] * n, macro=[0.60] * n)
    state_high = PoreNetworkState.empty(n)
    PoreNetworkModule(PoreNetworkParams(), state_high).compute(profile, agg_high)

    # Both must sum to saturation
    for i in range(n):
        assert abs(state_low.total_porosity(i) - profile.layers[i].saturation) < 1e-6
        assert abs(state_high.total_porosity(i) - profile.layers[i].saturation) < 1e-6

    # High MWD → more macropores
    assert state_high.macro[0] > state_low.macro[0], (
        f"High MWD macro {state_high.macro[0]:.4f} should exceed "
        f"low MWD macro {state_low.macro[0]:.4f}"
    )


# ---------- AC: Event emitted ----------


def test_event_emitted_on_compute() -> None:
    bus = EventBus()
    events: list[PoreNetworkComputed] = []
    bus.subscribe(PoreNetworkComputed, events.append)

    profile = _make_profile("loam")
    state = PoreNetworkState.empty(3)
    module = PoreNetworkModule(PoreNetworkParams(), state, event_bus=bus)
    module.compute(profile)

    assert len(events) == 3, "One event per layer"
    assert events[0].layer == 0
    assert events[0].macro > 0
    assert events[0].connectivity > 0


# ---------- AC: No event bus is OK ----------


def test_compute_without_event_bus() -> None:
    profile = _make_profile("sand")
    state = PoreNetworkState.empty(3)
    module = PoreNetworkModule(PoreNetworkParams(), state, event_bus=None)
    module.compute(profile)
    assert state.macro[0] > 0.1, "Sand should have substantial macropores"


# ---------- AC: All fractions non-negative ----------


@pytest.mark.parametrize("texture", ["sand", "sandy_loam", "loam", "clay_loam", "clay"])
def test_all_fractions_non_negative(texture: str) -> None:
    profile = _make_profile(texture)
    state = PoreNetworkState.empty(3)
    PoreNetworkModule(PoreNetworkParams(), state).compute(profile)

    for i in range(3):
        assert state.macro[i] >= 0.0
        assert state.meso[i] >= 0.0
        assert state.micro[i] >= 0.0
        assert state.crypto[i] >= 0.0


# ---------- Integration: pore distribution with real presets ----------


def test_pore_fractions_with_loaded_presets() -> None:
    """Run pore computation on every soil profile in presets."""
    from pathlib import Path

    presets_path = Path("data/soils/presets.yaml")
    if not presets_path.exists():
        pytest.skip("Soil presets not found")
    lib = load_soil_presets(presets_path)
    params = PoreNetworkParams()

    for name, profile in lib.soils.items():
        n = len(profile.layers)
        state = PoreNetworkState.empty(n)
        agg = SoilAggregationState.from_layers(n)
        PoreNetworkModule(params, state).compute(profile, agg)

        for i, layer in enumerate(profile.layers):
            total = state.total_porosity(i)
            assert (
                abs(total - layer.saturation) < 1e-6
            ), f"{name} layer {i}: pore sum {total:.4f} != sat {layer.saturation}"
            assert 0.0 <= state.connectivity[i] <= 1.0
