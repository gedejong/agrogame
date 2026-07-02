"""Shared canopy parameters used by both plant- and soil-side modules.

Lives under ``agrogame.params`` so the plant package can import without
crossing into ``agrogame.soil`` (#300, ADR-008). The cardinal-temperature
helper that originally accompanied the dataclass stays with the soil-side
canopy module — it's a runtime utility, not a parameter type.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanopyParams:
    """Frozen canopy parameters: light interception, RUE, LAI dynamics, senescence."""

    extinction_coefficient_k: float  # unitless Beer-Lambert k
    radiation_use_efficiency_g_per_mj: float  # g biomass per MJ intercepted PAR
    specific_leaf_area_m2_per_g: float  # SLA
    lai_max: float
    senescence_rate_per_day: float = 0.0
    initial_lai_at_emergence: float = 0.1  # LAI bootstrap at emergence
    senescence_vegetative_fraction: float = (
        0.1  # fraction of senescence rate during veg stage
    )
    # Cardinal temperatures for RUE scaling (DSSAT/APSIM style)
    temp_base_c: float = 8.0  # below this, temp_factor = 0
    temp_opt_c: float = 30.0  # at this, temp_factor = 1
    temp_max_c: float = 42.0  # above this, temp_factor = 0
    # Water stress feedback (AGRO-82)
    vpd_rue_ref_kpa: float = 1.5  # VPD above which RUE is reduced
    vpd_rue_slope: float = 0.1  # fractional RUE reduction per kPa above ref
    wilt_stress_threshold: float = 0.3  # stress below this triggers damage
    wilt_days_for_damage: int = 5  # consecutive days below threshold
    wilt_lai_loss_fraction: float = 0.1  # fraction of LAI lost per damage event
    stress_memory_days: int = 7  # window for running-average stress
    # Biomass partitioning: fraction of daily biomass allocated to leaves
    leaf_fraction_vegetative: float = 0.7
    leaf_fraction_flowering: float = 0.4
    leaf_fraction_grain_fill: float = 0.15
    # Stage-gated senescence multipliers
    senescence_flowering_fraction: float = 0.5  # moderate senescence at flowering
    senescence_grain_fill_max: float = 2.0  # peak multiplier at end of grain fill
    grain_fill_duration_gdd: float = 900.0  # GDD span over which senescence ramps
    # Harvest index: fraction of daily biomass allocated to grain during grain fill
    # Typical: maize 0.50, wheat 0.45, rice 0.45, sorghum 0.35 (DSSAT/APSIM)
    # Only used by the legacy fixed-HI path (when grains_per_g_source == 0).
    harvest_index: float = 0.45
    # --- Sink-source grain model (#321) -----------------------------------
    # CERES-style two-stage grain formation. When grains_per_g_source > 0 the
    # canopy replaces the fixed-HI allocation with (a) a potential grain
    # NUMBER set by assimilate supply during a peri-anthesis critical window
    # and (b) grain FILLING limited by number x single-kernel rate. Harvest
    # index then becomes an emergent, bounded outcome rather than a fixed
    # input. grains_per_g_source == 0 keeps the legacy fixed-HI behaviour, so
    # non-grain presets (grape HI=0) and any un-migrated crop are unaffected.
    #
    # Grain number is proportional to crop growth rate around anthesis:
    # Andrade et al. 1999 (maize kernel number vs plant growth rate at
    # silking); Fischer 1985 (wheat grains vs spike growth); DSSAT CERES G1
    # coefficient analogue. Because that growth already integrates cold (via
    # the cardinal-temperature factor), water and N stress through the RUE
    # source term, all three stresses in the window reduce grain number.
    grains_per_g_source: float = 0.0  # grains m^-2 per g m^-2 of window assimilate
    grain_set_window_gdd: float = 200.0  # post-anthesis lag/critical window (GDD)
    # Potential final single-kernel weight (CERES G2). Total grain sink =
    # grain_number x potential_kernel_weight. Typical: wheat ~40-45 mg,
    # maize ~250-300 mg, rice ~25 mg, sorghum ~28 mg (Hay & Porter 2006).
    potential_kernel_weight_mg: float = 40.0
    # Potential single-kernel daily fill rate from current assimilate. Caps
    # how fast photosynthate flows to grain; post-anthesis heat/water stress
    # scales it down, lowering realised kernel weight. Reserves (stem
    # remobilisation) top grains up toward potential_kernel_weight.
    kernel_fill_rate_mg_per_grain_day: float = 1.0
    # Emergent-HI cap: cumulative grain may not exceed hi_max x total biomass
    # (cereal ceiling ~0.50-0.55; Hay & Porter 2006; Gebbing & Schnyder 1999).
    hi_max: float = 0.55
    # Stem remobilization: daily fraction of stem biomass moved to grain
    # during grain fill. Defaults to 0 (opt-in per crop).
    # Gebbing & Schnyder 1999: 30-50% of grain C from pre-anthesis reserves.
    # APSIM: stem_remobilisation_fraction parameter.
    remobilization_fraction: float = 0.0
    # Senescing-leaf remobilization: daily fraction of the (implied) leaf
    # pool remobilised to grain during grain fill (#321). Post-anthesis
    # grain carbon/nitrogen also comes from remobilised flag-leaf and canopy
    # protein as leaves senesce (Gebbing & Schnyder 1999). Internal transfer
    # (total biomass unchanged); sink-capped. Opt-in per crop; used only by
    # the sink-source model. Defaults to 0.
    leaf_remob_fraction: float = 0.0
    # Extreme weather damage thresholds (AGRO-34)
    # Frost: LAI loss when tmin < threshold during EMERGED-FLOWERING.
    # Severity-proportional: loss = LAI * frac * clamp((thresh-tmin)/|thresh|)
    # DSSAT CERES: maize 0C, wheat -2C (Hatfield & Prueger 2015)
    frost_threshold_c: float = 0.0
    frost_damage_fraction: float = 0.3
    # Heat: grain reduction when tmax > threshold during FLOWERING.
    # DSSAT CERES heat stress on grain set (Hatfield & Prueger 2015)
    heat_damage_threshold_c: float = 35.0
    heat_grain_reduction_fraction: float = 0.5
    # Waterlogging: LAI loss after consecutive saturated days.
    # Setter & Waters 2003: root oxygen stress after 2-3 days saturation.
    waterlog_days_for_damage: int = 3
    waterlog_lai_loss_fraction: float = 0.15
