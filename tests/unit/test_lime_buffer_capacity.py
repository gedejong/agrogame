"""Buffer-capacity lime response and its downstream couplings (#465).

Covers the science half of the lime player action: the lime requirement per
unit soil mass for each texture class, texture ordering, pH clamping, and the
phosphorus and micronutrient responses a pH change drives.

Literature anchors for the buffer capacities asserted here:
  * Curtin & Rostad (1997), Can. J. Soil Sci. 77:621-626
  * Aitken & Moody (1994), Aust. J. Soil Res. 32:975-984
  * Shoemaker, McLean & Pratt (1961), SSSAJ 25:274-277 (buffer-method basis)
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.events import EventBus
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.chemistry import (
    ChemistryParams,
    ChemistryState,
    LayerBufferProperties,
    SoilChemistryModule,
)
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.micronutrients.constants import PH_AVAIL_FE, PH_AVAIL_ZN
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.phosphorus.state import SoilPhosphorusState
from agrogame.soil.water.types import DailyDrivers

# Published pH buffer capacity (cmol(H+)/kg soil per pH unit) converted at
# 50 g CaCO3 per mol of charge neutralised -> g CaCO3 per kg soil per pH:
#   sands  1-2 cmol -> 0.5-1.0 g/kg
#   loams  3-5 cmol -> 1.5-2.5 g/kg
#   clays  5-8 cmol -> 2.5-4.0 g/kg
_LIME_REQUIREMENT_BANDS_G_PER_KG: dict[str, tuple[float, float]] = {
    "sandy_arid": (0.5, 1.0),
    "sandy_temperate": (0.5, 1.0),
    "sandy_loam_temperate": (1.5, 2.5),
    "loam_temperate": (1.5, 2.5),
    "clay_temperate": (2.5, 4.0),
    "clay_netherlands": (2.5, 4.0),
}


def _orchestrator(preset_key: str) -> FullSimulationOrchestrator:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    return FullSimulationOrchestrator(lib.soils[preset_key])


def _layer_module(
    clay_pct: float,
    organic_matter_pct: float,
    *,
    base_ph: float,
    depth_cm: float = 25.0,
    bulk_density_g_cm3: float = 1.45,
) -> SoilChemistryModule:
    """A one-layer chemistry module at a chosen starting pH.

    Built directly rather than from a preset because no shipped preset starts
    acid or alkaline — per-preset initial pH is split out as #481.
    """
    return SoilChemistryModule(
        ChemistryParams(),
        ChemistryState.from_layers(1, base_ph=base_ph),
        EventBus(),
        layer_properties=[
            LayerBufferProperties(
                depth_cm=depth_cm,
                bulk_density_g_cm3=bulk_density_g_cm3,
                clay_pct=clay_pct,
                organic_matter_pct=organic_matter_pct,
            )
        ],
    )


# --- AC 5: lime requirement per unit soil mass, by texture class -----------
@pytest.mark.parametrize(
    ("preset_key", "band"), sorted(_LIME_REQUIREMENT_BANDS_G_PER_KG.items())
)
def test_lime_requirement_per_kg_soil_in_published_band(
    preset_key: str, band: tuple[float, float]
) -> None:
    """Layer-0 lime requirement per pH unit lands in its texture's band.

    Stated per unit soil mass, not t/ha, because the model's layer 0 is
    25-30 cm while published lime tables assume a 15-20 cm plough layer.
    """
    orch = _orchestrator(preset_key)
    layer = orch.profile.layers[0]
    soil_mass_kg_ha = layer.depth_cm * layer.bulk_density_g_cm3 * 1.0e5
    lr_kg_ha = orch.chem.lime_requirement_kg_ha_per_ph(0)
    g_per_kg = lr_kg_ha * 1000.0 / soil_mass_kg_ha
    lo, hi = band
    assert lo <= g_per_kg <= hi, (
        f"{preset_key} needs {g_per_kg:.2f} g CaCO3/kg soil per pH unit, "
        f"outside the published band {lo}-{hi}"
    )


def test_buffer_capacity_rises_with_clay_and_organic_matter() -> None:
    """pHBC increases in both drivers, which is why liming differs by soil."""
    base = _layer_module(22.0, 2.0, base_ph=6.0)
    more_clay = _layer_module(40.0, 2.0, base_ph=6.0)
    more_om = _layer_module(22.0, 4.0, base_ph=6.0)
    assert more_clay.ph_buffer_capacity_cmol_kg(0) > base.ph_buffer_capacity_cmol_kg(0)
    assert more_om.ph_buffer_capacity_cmol_kg(0) > base.ph_buffer_capacity_cmol_kg(0)


def test_unconfigured_layer_raises() -> None:
    """A missing soil-property entry fails loudly rather than guessing."""
    chem = SoilChemistryModule(
        ChemistryParams(), ChemistryState.from_layers(2, base_ph=6.8), EventBus()
    )
    with pytest.raises(ValueError, match="No soil buffer properties for layer 0"):
        chem.apply_lime(0, 1000.0)


def test_layer_buffer_properties_validate_inputs() -> None:
    with pytest.raises(ValueError, match="depth_cm"):
        LayerBufferProperties(0.0, 1.4, 20.0, 2.0)
    with pytest.raises(ValueError, match="bulk_density_g_cm3"):
        LayerBufferProperties(25.0, 0.0, 20.0, 2.0)
    with pytest.raises(ValueError, match="clay_pct"):
        LayerBufferProperties(25.0, 1.4, 120.0, 2.0)
    with pytest.raises(ValueError, match="organic_matter_pct"):
        LayerBufferProperties(25.0, 1.4, 20.0, -1.0)


# --- AC 6: texture ordering -----------------------------------------------
def test_clay_rises_less_than_sand_at_the_same_rate() -> None:
    """At 2 t/ha, a clay topsoil moves strictly less than a sandy one."""
    rate = 2000.0
    deltas: dict[str, float] = {}
    for key in ("clay_temperate", "sandy_temperate"):
        orch = _orchestrator(key)
        before = orch.chem.ph_by_layer[0]
        orch.apply_lime(rate, 0)
        deltas[key] = orch.chem.ph_by_layer[0] - before
    assert deltas["clay_temperate"] > 0.0
    assert deltas["sandy_temperate"] > 0.0
    assert deltas["clay_temperate"] < deltas["sandy_temperate"]


# --- AC 7: clamping --------------------------------------------------------
def test_absurd_rate_saturates_at_ceiling() -> None:
    orch = _orchestrator("loam_temperate")
    orch.apply_lime(50_000.0, 0)  # 50 t/ha
    ph = orch.chem.ph_by_layer[0]
    assert ph == pytest.approx(ChemistryParams().ph_ceiling)
    assert ph <= ChemistryParams().ph_ceiling


def test_non_positive_rate_and_bad_layer_are_handled() -> None:
    orch = _orchestrator("loam_temperate")
    before = list(orch.chem.ph_by_layer)
    orch.apply_lime(0.0, 0)
    orch.apply_lime(-500.0, 0)
    assert orch.chem.ph_by_layer == before
    with pytest.raises(ValueError, match="out of range"):
        orch.apply_lime(1000.0, 99)


# --- AC 8: phosphorus coupling --------------------------------------------
def test_liming_an_acid_layer_improves_p_availability_and_cuts_fixation() -> None:
    """pH 5.0 -> 6.5 lifts P availability and suppresses the fixation flux."""
    chem = _layer_module(22.0, 2.0, base_ph=5.0)
    # Rate that lifts the layer by exactly 1.5 pH units.
    chem.apply_lime(0, 1.5 * chem.lime_requirement_kg_ha_per_ph(0))
    limed_ph = chem.ph_by_layer[0]
    assert limed_ph == pytest.approx(6.5, abs=1e-9)

    avail_acid = PhosphorusCycle._ph_availability(5.0)
    avail_limed = PhosphorusCycle._ph_availability(limed_ph)
    assert avail_limed - avail_acid >= 0.2

    def _daily_fixed(ph: float) -> float:
        lib = load_soil_presets(Path("soils/presets.yaml"))
        state = SoilPhosphorusState(lib.soils["loam_temperate"])
        cycle = PhosphorusCycle(EventBus(), state)
        return cycle._fix_layer(0, ph)

    fixed_acid = _daily_fixed(5.0)
    fixed_limed = _daily_fixed(limed_ph)
    assert fixed_acid > 0.0
    assert (
        fixed_limed <= 0.7 * fixed_acid
    ), f"fixation only fell from {fixed_acid:.4f} to {fixed_limed:.4f} kg/ha/day"


# --- AC 9: micronutrient coupling -----------------------------------------
def _interp(ph: float, table: list[tuple[float, float]]) -> float:
    from agrogame.soil.micronutrients.cycle import _interpolate_ph

    return _interpolate_ph(ph, table)


def test_over_liming_to_ph_8_suppresses_zinc_and_iron() -> None:
    """pH 6.5 -> 8.0 drops the equilibrium Zn target >=50 % and Fe >=60 %.

    The pH multiplier is the only pH-dependent factor in the availability
    target (total x base fraction x pH multiplier x OM factor), so the drop
    in the multiplier is the drop in the target.
    """
    chem = _layer_module(22.0, 2.0, base_ph=6.5)
    chem.apply_lime(0, 1.5 * chem.lime_requirement_kg_ha_per_ph(0))
    limed_ph = chem.ph_by_layer[0]
    assert limed_ph == pytest.approx(8.0, abs=1e-9)

    zn_drop = 1.0 - _interp(limed_ph, PH_AVAIL_ZN) / _interp(6.5, PH_AVAIL_ZN)
    fe_drop = 1.0 - _interp(limed_ph, PH_AVAIL_FE) / _interp(6.5, PH_AVAIL_FE)
    assert zn_drop >= 0.50, f"Zn fell only {zn_drop:.1%}"
    assert fe_drop >= 0.60, f"Fe fell only {fe_drop:.1%}"


# --- Multi-cycle: lime survives a season boundary -------------------------
def test_lime_effect_persists_and_repeats_across_two_seasons() -> None:
    """Two full crop cycles: the pH lift carries over and lime still works.

    ``reset_crop`` clears every event subscription and rebuilds the module
    graph, so this is the path where a lost ``LimeApplied`` subscription or a
    dropped layer-properties wiring would silently disable liming from season
    two onward.
    """
    from agrogame.plant.presets import load_crop_presets

    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    maize = crops.get_preset("maize", "netherlands_temperate")
    orch = _orchestrator("loam_temperate")
    orch.reset_crop(maize)

    start_ph = orch.chem.ph_by_layer[0]
    deltas: list[float] = []
    for season in range(2):
        before = orch.chem.ph_by_layer[0]
        orch.apply_lime(2500.0, 0)
        deltas.append(orch.chem.ph_by_layer[0] - before)
        for day in range(30):
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=2.0),
                tmin_c=10.0,
                tmax_c=20.0,
                shortwave_mj_m2=15.0,
                sim_date=date(2024 + season, 5, 1 + day),
            )
        orch.reset_crop(maize)

    # 2.5 t/ha on loam_temperate: ~8.5 t/ha per pH unit -> roughly +0.3.
    for delta in deltas:
        assert 0.25 <= delta <= 0.40, f"unexpected lime response {delta:+.3f} pH"
    # The lift survives both season boundaries (daily buffering toward 6.8
    # erodes it only slowly, 0.1 %/day).
    assert orch.chem.ph_by_layer[0] > start_ph + 0.4
