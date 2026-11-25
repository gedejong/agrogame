"""N-cycle proton budget and its conversion to pH (#492, ADR-020).

Stoichiometry per mol N (Bolan, Hedley & White 1991, Plant Soil 134:53-63;
Helyar & Porter 1989, in Robson (ed.) Soil Acidity and Plant Growth): urea
hydrolysis and ammonification -1, nitrification +2, NO3- uptake -1, NH4+
uptake +1, denitrification -1, NH3 volatilisation +1. Each case below feeds
one layer exactly 1 kmol N (14.007 kg) through a known path and asserts the
net H+ that path must release.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import pytest

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.chemistry import (
    ChemistryParams,
    ChemistryRuntime,
    ChemistryState,
    LayerBufferProperties,
    SoilChemistryModule,
    SoilPHUpdated,
)
from agrogame.soil.models import SoilLayer, SoilProfile
from agrogame.soil.nitrogen import (
    NitrogenCycle,
    NitrogenRateParams,
    ProtonLoadOccurred,
    SoilNitrogenState,
)
from agrogame.soil.nitrogen.constants import (
    N_KG_PER_KMOL,
    NH4_UPTAKE_RESIDUAL_MG_KG,
    NO3_UPTAKE_RESIDUAL_MG_KG,
)
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.nitrogen.runtime import NitrogenRuntime
from agrogame.soil.phosphorus.events import PhosphorusFixationOccurred
from agrogame.soil.som.events import SOMDecomposed
from agrogame.soil.water.events import WaterDrained

KMOL_N = N_KG_PER_KMOL  # 1 kmol N in kg N
_EXACT = 1e-12

# Every rate either completes in one day (first-order fraction capped at 1)
# or is switched off, so each path below moves exactly 1 kmol N.
_OFF = NitrogenRateParams(
    nitrification_base_rate=0.0,
    denitrification_base_rate=0.0,
    volatilization_base_rate=0.0,
    volatilization_max_rate=0.0,
)
_NITRIFY = NitrogenRateParams(
    nitrification_base_rate=100.0,
    nitrification_max_rate=1.0,
    denitrification_base_rate=0.0,
    volatilization_base_rate=0.0,
    volatilization_max_rate=0.0,
)
_DENITRIFY = NitrogenRateParams(
    nitrification_base_rate=0.0,
    denitrification_base_rate=100.0,
    volatilization_base_rate=0.0,
    volatilization_max_rate=0.0,
)
_VOLATILIZE = NitrogenRateParams(
    nitrification_base_rate=0.0,
    denitrification_base_rate=0.0,
    volatilization_base_rate=100.0,
    volatilization_max_rate=1.0,
)
_MINERALIZE = NitrogenRateParams(
    mineralization_base_rate=100.0,
    nitrification_base_rate=0.0,
    denitrification_base_rate=0.0,
    volatilization_base_rate=0.0,
    volatilization_max_rate=0.0,
)


_N_LAYERS = 3  # SoilProfile's minimum; the paths below use layers 0 and 1


def _profile() -> SoilProfile:
    layer: dict[str, Any] = {
        "depth_cm": 40,  # 3 x 40 cm: SoilProfile needs >= 100 cm
        "texture": "loam",
        "field_capacity": 0.30,
        "wilting_point": 0.12,
        "saturation": 0.45,
        "bulk_density_g_cm3": 1.45,
        "ksat_mm_per_hour": 20,
        "organic_matter_pct": 2.0,
        "initial_no3_kg_ha": 0.0,
        "initial_nh4_kg_ha": 0.0,
        "initial_p_kg_ha": 25.0,
    }
    return SoilProfile(
        name="proton-test", layers=[SoilLayer(**layer) for _ in range(_N_LAYERS)]
    )


def _residual(mg_kg: float, layer: int = 0) -> float:
    """N (kg/ha) uptake leaves in a fixture layer: mg/kg x BD x depth_cm / 10 (#694)."""
    ly = _profile().layers[layer]
    return mg_kg * ly.bulk_density_g_cm3 * ly.depth_cm / 10.0


class _Budget:
    """A cycle with empty N pools that records every H+ it releases."""

    def __init__(self) -> None:
        self.bus = EventBus()
        profile = _profile()
        self.state = SoilNitrogenState(profile)
        self.state.organic_n = [0.0] * _N_LAYERS
        self.cycle = NitrogenCycle(self.bus, self.state, profile=cast(Any, profile))
        self.released = [0.0] * _N_LAYERS
        self.bus.subscribe(ProtonLoadOccurred, self._on_load)

    def _on_load(self, ev: ProtonLoadOccurred) -> None:
        self.released[ev.layer] += ev.h_kmol_ha

    def day(
        self,
        params: NitrogenRateParams,
        demand_kg_ha: float = 0.0,
        root_fractions: tuple[float, ...] = (1.0, 0.0, 0.0),
    ) -> None:
        """One day at 20 degC and pH 7 (temperature and pH factors 1), then day_end.

        Swaps the rate set between days so one cycle, with its pools and
        budget, can run a multi-step path one process at a time.
        """
        self.cycle._params = params
        self.cycle.daily_step(
            temperature_c=20.0,
            plant_demand_kg_ha=demand_kg_ha,
            root_fractions=list(root_fractions),
            ph_by_layer=[7.0] * _N_LAYERS,
        )
        self.cycle.release_proton_budget()
        assert self.cycle.pending_proton_load_kmol_ha == [0.0] * _N_LAYERS

    def net(self) -> float:
        """Layer-0 net H+ (kmol/ha); the other layers must have seen none."""
        assert self.released[1:] == [0.0] * (_N_LAYERS - 1)
        return self.released[0]


def _som_mineralised(layer: int, n_kg_ha: float) -> SOMDecomposed:
    return SOMDecomposed(
        layer=layer, pool="labile", decomposed_c_kg_ha=0.0, mineralized_n_kg_ha=n_kg_ha
    )


# --- AC5: N mass and proton consistency --------------------------------------


def test_urea_nitrified_then_taken_up_nets_one_per_residual_nitrate_n() -> None:
    """The N taken up is acid-neutral; the NO3 residual it leaves (#694) is +1 per N.

    The residual is urea N nitrified and left as nitrate, the identity of
    ``test_urea_nitrified_and_left_as_nitrate_releases_one_per_n``.
    """
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)  # -1
    b.day(_NITRIFY)  # +2
    assert b.state.no3[0] == pytest.approx(KMOL_N, abs=_EXACT)
    b.day(_OFF, demand_kg_ha=KMOL_N)  # NO3 uptake -1 per N taken
    no3_left = _residual(NO3_UPTAKE_RESIDUAL_MG_KG)
    assert b.state.no3[0] == pytest.approx(no3_left, abs=_EXACT)
    assert b.net() == pytest.approx(no3_left / KMOL_N, abs=_EXACT)


def test_urea_nitrified_and_left_as_nitrate_releases_one_per_n() -> None:
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)
    b.day(_NITRIFY)
    b.day(_OFF)
    assert b.net() == pytest.approx(1.0, abs=_EXACT)


def test_urea_volatilised_releases_no_net_acid() -> None:
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)  # -1
    b.day(_VOLATILIZE)  # +1
    assert b.state.nh4[0] == pytest.approx(0.0, abs=_EXACT)
    assert b.net() == pytest.approx(0.0, abs=_EXACT)


def test_som_n_nitrified_then_taken_up_nets_one_per_residual_nitrate_n() -> None:
    """As for urea: only the NO3 residual uptake leaves (#694) keeps its +1 per N."""
    b = _Budget()
    b.bus.emit(_som_mineralised(0, KMOL_N))  # ammonification -1
    b.cycle.release_proton_budget()
    b.day(_NITRIFY)  # +2
    b.day(_OFF, demand_kg_ha=KMOL_N)  # -1 per N taken
    no3_left = _residual(NO3_UPTAKE_RESIDUAL_MG_KG)
    assert b.state.no3[0] == pytest.approx(no3_left, abs=_EXACT)
    assert b.net() == pytest.approx(no3_left / KMOL_N, abs=_EXACT)


# The remaining terms: NH4 uptake, denitrification, self-mineralisation.


def test_urea_taken_up_as_ammonium_nets_minus_one_per_residual_ammonium_n() -> None:
    """The NH4 taken up is acid-neutral; the NH4 residual (#694) keeps its -1 per N.

    The residual is hydrolysed urea N that NH4 uptake has not yet returned.
    """
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)  # -1
    b.day(_OFF, demand_kg_ha=KMOL_N)  # NH4 uptake +1 per N taken
    nh4_left = _residual(NH4_UPTAKE_RESIDUAL_MG_KG)
    assert b.state.nh4[0] == pytest.approx(nh4_left, abs=_EXACT)
    assert b.net() == pytest.approx(-nh4_left / KMOL_N, abs=_EXACT)


def test_urea_nitrified_then_denitrified_releases_no_net_acid() -> None:
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)  # -1
    b.day(_NITRIFY)  # +2
    b.cycle.set_aerobic_fraction_override([0.0])  # layer 0 fully anaerobic
    b.day(_DENITRIFY)  # -1
    assert b.state.no3[0] == pytest.approx(0.0, abs=_EXACT)
    assert b.net() == pytest.approx(0.0, abs=_EXACT)


def test_self_mineralisation_consumes_one_per_n() -> None:
    """The standalone cycle's own ammonification (disabled in the orchestrator)."""
    b = _Budget()
    b.state.organic_n[0] = KMOL_N
    b.day(_MINERALIZE)
    assert b.state.nh4[0] == pytest.approx(KMOL_N, abs=_EXACT)
    assert b.net() == pytest.approx(-1.0, abs=_EXACT)


def test_acidity_stays_where_nitrate_was_produced() -> None:
    """No leaching term: nitrate moved down and taken up there.

    Layer 0 keeps the +1 of nitrification without uptake; layer 1 gets the -1
    per N of nitrate uptake, which stops at layer 1's NO3 residual (#694). The
    profile total equals that of uptake in place: +1 per N of the residual.
    """
    b = _Budget()
    b.cycle.apply_urea(0, KMOL_N)
    b.day(_NITRIFY)
    # 100 mm through a layer with the 100 mm nominal storage moves all NO3.
    b.bus.emit(WaterDrained(from_layer=0, to_layer=1, amount_mm=100.0))
    assert b.state.no3 == pytest.approx([0.0, KMOL_N, 0.0], abs=_EXACT)
    b.day(_OFF, demand_kg_ha=KMOL_N, root_fractions=(0.0, 1.0, 0.0))
    no3_left = _residual(NO3_UPTAKE_RESIDUAL_MG_KG, layer=1)
    assert b.state.no3 == pytest.approx([0.0, no3_left, 0.0], abs=_EXACT)
    taken = (KMOL_N - no3_left) / KMOL_N
    assert b.released == pytest.approx([1.0, -taken, 0.0], abs=_EXACT)
    assert sum(b.released) == pytest.approx(no3_left / KMOL_N, abs=_EXACT)


def test_ammonium_nitrate_releases_nothing_at_application() -> None:
    b = _Budget()
    b.cycle.apply_ammonium_nitrate(0, 2.0 * KMOL_N)
    b.cycle.release_proton_budget()
    assert b.net() == 0.0


# --- AC12: release semantics -------------------------------------------------


def test_urea_hydrolysis_is_released_at_application_not_held() -> None:
    b = _Budget()
    b.cycle.apply_urea(0, 100.0)
    assert b.net() == pytest.approx(-100.0 / N_KG_PER_KMOL, abs=_EXACT)
    assert b.cycle.pending_proton_load_kmol_ha == [0.0] * _N_LAYERS


def test_release_emits_once_per_nonzero_layer_and_clears() -> None:
    b = _Budget()
    seen: list[ProtonLoadOccurred] = []
    b.bus.subscribe(ProtonLoadOccurred, seen.append)
    b.bus.emit(_som_mineralised(2, KMOL_N))
    assert b.cycle.pending_proton_load_kmol_ha == pytest.approx([0.0, 0.0, -1.0])
    b.cycle.release_proton_budget()
    assert [(ev.layer, ev.h_kmol_ha) for ev in seen] == [(2, pytest.approx(-1.0))]
    b.cycle.release_proton_budget()  # nothing pending: nothing emitted
    assert len(seen) == 1


def _tick(phase: str) -> DayTick:
    return DayTick(sim_date=date(2024, 5, 1), phase=phase)


def test_runtime_releases_at_day_end_only() -> None:
    b = _Budget()
    NitrogenRuntime(b.bus, b.cycle)
    b.bus.emit(_som_mineralised(0, KMOL_N))
    for phase in ("chemistry", "water", "canopy"):
        b.bus.emit(_tick(phase))
    assert b.released == [0.0] * _N_LAYERS
    b.bus.emit(_tick("day_end"))
    assert b.net() == pytest.approx(-1.0, abs=_EXACT)
    assert b.cycle.pending_proton_load_kmol_ha == [0.0] * _N_LAYERS


# --- Conversion to pH --------------------------------------------------------

# loam_temperate layer 0: 25 cm, BD 1.45, 22 % clay, 2.0 % OM.
_LOAM = LayerBufferProperties(
    depth_cm=25.0, bulk_density_g_cm3=1.45, clay_pct=22.0, organic_matter_pct=2.0
)
_SAND = LayerBufferProperties(
    depth_cm=25.0, bulk_density_g_cm3=1.55, clay_pct=5.0, organic_matter_pct=1.0
)


def _chem(
    base_ph: float = 6.8, layers: tuple[LayerBufferProperties, ...] = (_LOAM, _LOAM)
) -> tuple[SoilChemistryModule, EventBus]:
    bus = EventBus()
    chem = SoilChemistryModule(
        ChemistryParams(),
        ChemistryState.from_layers(len(layers), base_ph=base_ph),
        bus,
        layer_properties=list(layers),
    )
    return chem, bus


def test_buffer_is_phbc_times_soil_mass() -> None:
    """kmol H+/ha per pH unit = pHBC [cmol/kg/pH] x mass [kg/ha] / 1e5."""
    chem, _ = _chem()
    phbc = chem.ph_buffer_capacity_cmol_kg(0)
    assert chem.proton_buffer_kmol_ha_per_ph(0) == pytest.approx(
        phbc * _LOAM.soil_mass_kg_ha / 1e5, rel=1e-12
    )
    # ~4.7 cmol/kg/pH (loam band 3-5; Curtin & Rostad 1997) over 3625 t/ha.
    assert 150.0 < chem.proton_buffer_kmol_ha_per_ph(0) < 190.0


def test_proton_load_shifts_ph_through_the_buffer() -> None:
    chem, bus = _chem()
    seen: list[SoilPHUpdated] = []
    bus.subscribe(SoilPHUpdated, seen.append)
    buffer = chem.proton_buffer_kmol_ha_per_ph(0)
    chem.apply_proton_load(0, 5.0)
    assert chem.ph_by_layer == pytest.approx([6.8 - 5.0 / buffer, 6.8], abs=_EXACT)
    chem.apply_proton_load(0, -5.0)  # consumption alkalinises by the same step
    assert chem.ph_by_layer[0] == pytest.approx(6.8, abs=_EXACT)
    # Only the changed layer is re-published.
    assert [ev.layer for ev in seen] == [0, 0]


def test_proton_load_and_lime_share_one_scale() -> None:
    """R kg CaCO3 neutralises R / 50 kmol H+ (50 g CaCO3 per mol charge)."""
    limed, _ = _chem()
    loaded, _ = _chem()
    limed.apply_lime(0, 2000.0)
    loaded.apply_proton_load(0, -2000.0 / 50.0)
    assert loaded.ph_by_layer[0] == pytest.approx(limed.ph_by_layer[0], abs=_EXACT)


def test_sand_moves_further_than_loam_for_the_same_load() -> None:
    chem, _ = _chem(layers=(_LOAM, _SAND))
    chem.apply_proton_load(0, 5.0)
    chem.apply_proton_load(1, 5.0)
    loam_drop, sand_drop = (6.8 - ph for ph in chem.ph_by_layer)
    assert sand_drop > 2.0 * loam_drop > 0.0


def test_proton_load_clamps_to_floor_and_ceiling() -> None:
    chem, _ = _chem()
    chem.apply_proton_load(0, 1.0e6)
    chem.apply_proton_load(1, -1.0e6)
    assert chem.ph_by_layer == pytest.approx([4.0, 9.0], abs=_EXACT)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_load_raises(bad: float) -> None:
    chem, _ = _chem()
    with pytest.raises(ValueError, match="finite"):
        chem.apply_proton_load(0, bad)


def test_load_on_unconfigured_layer_raises() -> None:
    chem, _ = _chem()
    with pytest.raises(ValueError, match="layer 5"):
        chem.apply_proton_load(5, 1.0)


# --- AC1-3: the three proxies are gone ---------------------------------------


def test_proxies_removed() -> None:
    import agrogame.soil.chemistry as chemistry

    for name in (
        "apply_phosphorus_fixation",
        "apply_nutrient_leaching",
        "apply_acidifying_fertilizer",
    ):
        assert not hasattr(SoilChemistryModule, name), name
    params = ChemistryParams()
    for field in (
        "p_fixation_ph_delta",
        "no3_leach_ph_delta",
        "acidifying_ph_delta_per_kg_ha",
    ):
        assert not hasattr(params, field), field
    assert not hasattr(chemistry, "AcidifyingFertilizerApplied")


def test_runtime_ignores_leaching_and_p_fixation() -> None:
    chem, bus = _chem()
    ChemistryRuntime(bus, chem)
    bus.emit(NutrientLeached(nutrient="NO3", amount_kg_ha=50.0, layer=1))
    bus.emit(PhosphorusFixationOccurred(layer=0, amount_fixed_kg_ha=5.0))
    assert chem.ph_by_layer == [6.8, 6.8]
    bus.emit(ProtonLoadOccurred(layer=1, h_kmol_ha=1.0))
    assert chem.ph_by_layer[1] < 6.8
