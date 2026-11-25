from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.params.memory import RuntimeMemory
from agrogame.params.phenology import PhenologyStage
from agrogame.soil.phenology import GddAccumulated, StageChanged
from .events import Harvested
from .module import CanopyModule
from .params import cardinal_temp_factor
from agrogame.plant.events import WaterStressComputed, NutrientStressComputed
from agrogame.weather.utils import saturation_vapor_pressure_kpa

if TYPE_CHECKING:
    from agrogame.plant.roots.events import RootDepthChanged

# Stages in which a frost day damages the canopy (``_check_frost_damage``).
# Shared with the game-layer frost notice (#470) so an alert can never claim a
# vulnerability the damage model does not apply.
FROST_VULNERABLE_STAGES: frozenset[PhenologyStage] = frozenset(
    {PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE, PhenologyStage.FLOWERING}
)


@dataclass
class CanopyRuntime(RuntimeMemory):
    """Wire CanopyModule to the EventBus; subscribes to DayTick + stress events.

    It also steps a read-only **potential-production shadow canopy** (#660):
    the same ``CanopyModule`` and params, with no event bus, so it emits nothing
    and nothing reads it but the API's ``growth_vs_potential``. Production
    levels follow van Ittersum & Rabbinge (1997, Field Crops Res. 52:197-208):
    the shadow keeps the *defining* factors (radiation, temperature, and the
    VPD RUE factor, which acts with water unlimited), drops the *limiting*
    factors (water and nutrients: ``water_stress`` is the VPD factor alone and
    ``n_stress`` is 1) and the *reducing* factors (no frost, waterlogging or
    drought-senescence damage). It follows the actual canopy's stage and GDD
    and its harvest, so the emergence bootstrap, the grain-fill anchors and a
    harvest cut match. Actual over potential shoot biomass is then the
    season's realised share of potential (van Ittersum et al. 2003, Eur. J.
    Agron. 18:201-234). The shadow is saved by ``Patch.to_dict`` and rebuilt
    with the runtime on a crop change.
    """

    event_bus: EventBus
    canopy: CanopyModule
    # Below-ground share of the daily assimilate pool (#337). Sourced from the
    # frozen RootParams.root_allocation_fraction and wired in by the
    # orchestrator; the canopy withholds this share from shoot/grain each day.
    root_allocation_fraction: float = 0.0
    _last_water: float = 1.0
    _last_n: float = 1.0
    _last_p: float = 1.0
    _last_fe: float = 1.0
    _last_zn: float = 1.0
    _last_mn: float = 1.0
    _last_s: float = 1.0
    # Initialized properly in __post_init__ using configurable window size
    _stress_history: deque[float] = field(init=False)
    _consecutive_wilt_days: int = 0
    _consecutive_waterlog_days: int = 0
    _waterlogged_today: bool = False
    # Live rooting depth (cm) tracked from RootDepthChanged; drives the
    # FAO-56 TAW ∝ Zr rate modifier for drought senescence (#373).
    _root_depth_cm: float = field(init=False)
    # Potential-production shadow canopy (#660); see the class docstring.
    _potential: CanopyModule = field(init=False)
    # Saved with the patch (#577): yesterday's stresses, the running-mean
    # window, the wilt/waterlog counters and the live rooting depth.
    _MEMORY = (
        "_last_water",
        "_last_n",
        "_last_p",
        "_last_fe",
        "_last_zn",
        "_last_mn",
        "_last_s",
        "_stress_history",
        "_consecutive_wilt_days",
        "_consecutive_waterlog_days",
        "_waterlogged_today",
        "_root_depth_cm",
    )
    # All of it mirrors the crop, so a crop change resets it (#583).
    _CROP_MEMORY = _MEMORY

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(WaterStressComputed, self._on_water_stress)
        self.event_bus.subscribe(NutrientStressComputed, self._on_nutrient_stress)
        from agrogame.soil.water.events import WaterloggingDetected
        from agrogame.plant.roots.events import RootDepthChanged

        self.event_bus.subscribe(WaterloggingDetected, self._on_waterlogging)
        self.event_bus.subscribe(RootDepthChanged, self._on_root_depth)
        self._stress_history = deque(maxlen=self.canopy.params.stress_memory_days)
        # Default to the reference depth so the modifier is neutral (factor 1.0)
        # until the root module reports a live depth.
        self._root_depth_cm = self.canopy.params.drought_senescence_ref_depth_cm
        # No bus: the shadow must never emit BiomassAccumulated (N/P demand)
        # or LAIUpdated. The runtime relays the events it follows.
        self._potential = CanopyModule(self.canopy.params, event_bus=None)
        self.event_bus.subscribe(StageChanged, self._on_potential_stage)
        self.event_bus.subscribe(GddAccumulated, self._on_potential_gdd)
        self.event_bus.subscribe(Harvested, self._on_potential_harvest)

    @property
    def potential(self) -> CanopyModule:
        """The read-only potential-production shadow canopy (#660)."""
        return self._potential

    def _on_potential_stage(self, ev: StageChanged) -> None:
        self._potential._on_stage_changed(ev)

    def _on_potential_gdd(self, ev: GddAccumulated) -> None:
        self._potential._on_gdd_accumulated(ev)

    def _on_potential_harvest(self, ev: Harvested) -> None:
        self._potential._on_harvest(ev)

    def _on_water_stress(self, ev: WaterStressComputed) -> None:
        self._last_water = max(0.0, min(1.0, float(ev.stress)))

    def _on_nutrient_stress(self, ev: NutrientStressComputed) -> None:
        s = max(0.0, min(1.0, float(ev.stress)))
        key = ev.nutrient.upper()
        if key == "N":
            self._last_n = s
        elif key == "P":
            self._last_p = s
        elif key == "FE":
            self._last_fe = s
        elif key == "ZN":
            self._last_zn = s
        elif key == "MN":
            self._last_mn = s
        elif key == "S":
            self._last_s = s

    def _compute_temp_factor(self, ev: DayTick) -> float:
        if ev.tmin_c is None or ev.tmax_c is None:
            return 1.0
        tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        p = self.canopy.params
        return cardinal_temp_factor(tmean, p.temp_base_c, p.temp_opt_c, p.temp_max_c)

    def _vpd_rue_factor(self, ev: DayTick) -> float:
        """Reduce RUE under high VPD using FAO-56 tmin-based dewpoint.

        VPD ≈ SVP(tmean) - SVP(tmin), following FAO-56 recommendation
        that tmin approximates dewpoint temperature. No circular
        dependency on water stress.
        """
        if ev.tmin_c is None or ev.tmax_c is None:
            return 1.0
        tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        vpd = saturation_vapor_pressure_kpa(tmean) - saturation_vapor_pressure_kpa(
            float(ev.tmin_c)
        )
        vpd = max(0.0, vpd)
        p = self.canopy.params
        excess = max(0.0, vpd - p.vpd_rue_ref_kpa)
        return max(0.2, 1.0 - p.vpd_rue_slope * excess)

    def _update_stress_memory(self, water_stress: float) -> float:
        """Track stress history and return running-average stress."""
        self._stress_history.append(water_stress)
        if not self._stress_history:
            return water_stress
        return sum(self._stress_history) / len(self._stress_history)

    def _on_waterlogging(self, _ev: object) -> None:
        """Mark today as waterlogged (consumed by _check_waterlogging)."""
        self._waterlogged_today = True

    def _on_root_depth(self, ev: RootDepthChanged) -> None:
        """Track live rooting depth for the drought-senescence rate modifier."""
        self._root_depth_cm = max(0.0, float(ev.new_cm))

    def _check_frost_damage(self, tmin_c: float) -> None:
        """Apply LAI loss on frost days during vulnerable stages.

        Severity is proportional to how far below the threshold:
        loss = LAI * fraction * clamp((threshold - tmin) / 10, 0, 1)
        Ref: DSSAT CERES frost kill; Hatfield & Prueger 2015.
        """
        if self.canopy._current_stage not in FROST_VULNERABLE_STAGES:
            return
        p = self.canopy.params
        if tmin_c >= p.frost_threshold_c:
            return
        # Severity scales linearly: 0 at threshold, 1.0 at 10C below threshold
        severity = min(1.0, (p.frost_threshold_c - tmin_c) / 10.0)
        loss = self.canopy.state.lai * p.frost_damage_fraction * severity
        self.canopy.state.lai = max(0.0, self.canopy.state.lai - loss)
        # Convert LAI loss to biomass using actual SLA (LAI = biomass * SLA)
        sla = p.specific_leaf_area_m2_per_g
        biomass_loss = loss / sla if sla > 0.0 else 0.0
        self.canopy.state.biomass_g_m2 = max(
            0.0, self.canopy.state.biomass_g_m2 - biomass_loss
        )
        if loss > 0.0:
            from agrogame.soil.canopy.events import FrostDamageApplied

            self.event_bus.emit(
                FrostDamageApplied(
                    lai_loss=loss,
                    biomass_loss_g_m2=biomass_loss,
                    tmin_c=tmin_c,
                    severity=severity,
                    threshold_c=p.frost_threshold_c,
                )
            )

    def _check_heat_damage(self, tmax_c: float) -> None:
        """Emit ``HeatDamageApplied`` when Tmax exceeds the crop's threshold.

        Exposure check only: it fires on a FLOWERING or GRAIN_FILL day with
        Tmax above ``heat_damage_threshold_c`` and changes no growth (the
        per-day grain cap it once returned was refilled from reserves and was
        retired in #664). Ref: Hatfield & Prueger 2015 (35 degC maize).
        """
        from agrogame.soil.phenology import PhenologyStage

        if self.canopy._current_stage not in (
            PhenologyStage.FLOWERING,
            PhenologyStage.GRAIN_FILL,
        ):
            return
        p = self.canopy.params
        if tmax_c <= p.heat_damage_threshold_c:
            return
        from agrogame.soil.canopy.events import HeatDamageApplied

        self.event_bus.emit(
            HeatDamageApplied(tmax_c=tmax_c, threshold_c=p.heat_damage_threshold_c)
        )

    def _check_waterlogging_damage(self) -> None:
        """Apply LAI loss after consecutive waterlogged days.

        Follows the wilt damage pattern: counter increments when
        waterlogged, resets when drained. Damage fires after threshold.
        Ref: Setter & Waters 2003 — root O2 stress under saturation.
        """
        p = self.canopy.params
        if self._waterlogged_today:
            self._consecutive_waterlog_days += 1
        else:
            self._consecutive_waterlog_days = 0
        self._waterlogged_today = False  # reset for next day
        if self._consecutive_waterlog_days >= p.waterlog_days_for_damage:
            loss = self.canopy.state.lai * p.waterlog_lai_loss_fraction
            self.canopy.state.lai = max(0.0, self.canopy.state.lai - loss)
            self._consecutive_waterlog_days = 0

    def _drought_depth_factor(self) -> float:
        """FAO-56 TAW ∝ Zr rate modifier for drought senescence (#373).

        Deeper roots reach a larger total-available-water pool, so a given
        Ta/Tp deficit senesces leaf area more slowly; a shallow-rooted
        seedling senesces faster (rapid seedling drought). The factor scales
        the daily senescence *rate* multiplicatively (not the onset
        threshold). Returns ``clamp(ref_depth / current_depth, min, max)``.
        Ref: FAO-56 TAW = (θ_FC − θ_WP) · Zr (Allen et al. 1998, Eq. 82).
        """
        p = self.canopy.params
        depth = max(1.0, self._root_depth_cm)
        factor = p.drought_senescence_ref_depth_cm / depth
        lo = p.drought_senescence_depth_factor_min
        hi = p.drought_senescence_depth_factor_max
        return max(lo, min(hi, factor))

    def _check_drought_senescence(self, water_stress: float) -> None:
        """Graded, per-unit-leaf drought leaf-senescence (#373).

        Replaces the old discrete N-day, size-independent 10%-of-LAI wilt
        step. Once stress has stayed below the onset threshold for the crop's
        tolerance lag (``wilt_days_for_damage``), a fraction of *current* LAI
        is senesced every day, scaled by stress severity
        ``(onset − Ta/Tp) / onset`` and the rooting-depth modifier. Because
        the loss is a fraction of current LAI it bites a small, vigorously
        growing canopy in the same relative terms as a large one, so net leaf
        area no longer climbs through a severe drought.

        Refs: FAO-56 Ks / TAW ∝ Zr (Allen et al. 1998); DSSAT CERES TURFAC /
        water-stress leaf senescence; APSIM ``swdef_senescence`` (Keating et
        al. 2003) — a graded daily per-unit-leaf rate, never a fixed step.

        Convention (#420, item 6a): senescence debits **LAI only**, not the
        biomass pool. The lost leaf area is treated as standing dead material
        retained on the plant until harvest, consistent with the existing
        canopy convention (LAI and biomass diverge under stress). This mirrors
        the LAI-only waterlogging path and deliberately differs from
        ``_check_frost_damage``, which does convert lost LAI to a biomass debit
        via SLA. Debiting a biomass pool here (option 6b) is deferred to a
        future issue as it would shift ``tests/integration/test_realism.py``
        yield ranges. Accordingly the emitted ``DroughtSenescenceApplied``
        diagnostic carries no ``biomass_loss_g_m2`` field.
        """
        p = self.canopy.params
        onset = p.wilt_stress_threshold
        if onset <= 0.0 or water_stress >= onset:
            self._consecutive_wilt_days = 0
            return
        self._consecutive_wilt_days += 1
        # Tolerance lag: leaves recover from brief wilting via turgor; only
        # sustained stress drives irreversible senescence (deeper-rooted crops
        # set a longer lag, e.g. winter wheat).
        if self._consecutive_wilt_days < p.wilt_days_for_damage:
            return
        severity = (onset - water_stress) / onset  # 0 at onset, →1 as Ta/Tp→0
        depth_factor = self._drought_depth_factor()
        rate = p.wilt_lai_loss_fraction * severity * depth_factor
        loss = self.canopy.state.lai * max(0.0, min(1.0, rate))
        self.canopy.state.lai = max(0.0, self.canopy.state.lai - loss)
        if loss > 0.0:
            from agrogame.soil.canopy.events import DroughtSenescenceApplied

            self.event_bus.emit(
                DroughtSenescenceApplied(
                    lai_loss=loss,
                    severity=severity,
                    depth_factor=depth_factor,
                )
            )

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "canopy":
            return
        par = 12.0 if ev.shortwave_mj_m2 is None else float(ev.shortwave_mj_m2)
        water = self._last_water
        n = self._last_n
        p = self._last_p
        avg_water = self._update_stress_memory(water)
        vpd_factor = self._vpd_rue_factor(ev)
        effective_water = avg_water * vpd_factor

        # Liebig minimum: N, P, S, and micronutrients (Fe, Zn, Mn)
        nutrient_stress = min(
            n, p, self._last_s, self._last_fe, self._last_zn, self._last_mn
        )
        tf = self._compute_temp_factor(ev)

        # Heat exposure event on flowering / grain-fill days (AGRO-34, #664)
        tmax = float(ev.tmax_c) if ev.tmax_c is not None else 25.0
        self._check_heat_damage(tmax)

        _ = self.canopy.daily_step(
            incident_shortwave_mj_m2=par,
            temp_factor=tf,
            water_stress=effective_water,
            n_stress=nutrient_stress,
            root_allocation_fraction=self.root_allocation_fraction,
        )
        # Damage checks (drought senescence, frost, waterlogging) — AGRO-34, #373
        self._check_drought_senescence(water)
        tmin = float(ev.tmin_c) if ev.tmin_c is not None else 10.0
        self._check_frost_damage(tmin)
        self._check_waterlogging_damage()
        # Potential production (#660): the same day's light, temperature and
        # VPD factor, water and nutrients unlimited, no damage applied.
        self._potential.daily_step(
            incident_shortwave_mj_m2=par,
            temp_factor=tf,
            water_stress=vpd_factor,
            n_stress=1.0,
            root_allocation_fraction=self.root_allocation_fraction,
        )
