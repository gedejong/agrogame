"""Field→Patch→Orchestrator hierarchy (ADR-002, AGRO-108).

FieldManager manages N fields, each with M patches. Each patch wraps
a FullSimulationOrchestrator with its own soil profile, crop, and
EventBus. The simulation engine is unchanged — this is a game-layer
coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any

from agrogame.events.recorder import EventRecorder
from agrogame.plant.nitrogen.state import PlantNitrogenState
from agrogame.plant.presets import CropPreset, load_crop_presets
from agrogame.plant.roots.types import RootState
from agrogame.soil.canopy.types import CanopyState
from agrogame.soil.phenology.types import PhenologyState
from agrogame.sim.management import ManagementPlan
from agrogame.sim.orchestrator import FullSimulationOrchestrator, SoilSnapshot
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.presets import load_climate_presets

# A field's patch area fractions must sum to 1.0 within this absolute tolerance,
# which admits fractions rounded to three places (3 x 0.333 = 0.999). The API
# checks a create request against the same bound (#552).
AREA_FRACTION_SUM_TOLERANCE = 0.01


@dataclass(frozen=True)
class PatchConfig:
    """Configuration for one patch within a field."""

    soil_profile_key: str
    crop_key: str
    climate_key: str
    area_fraction: float  # 0-1, must sum to 1.0 across field


@dataclass(frozen=True)
class PatchResult:
    """Harvest result for one patch."""

    patch_idx: int
    crop_key: str
    grain_g_m2: float
    grain_kg_ha: float
    soil_snapshot: SoilSnapshot


def _copy_fields(target: Any, source: Any) -> None:
    """Copy every dataclass field of ``source`` onto ``target`` in place (#515).

    Runtimes capture state objects when they are wired (``RootsRuntime`` and
    ``ETRuntime`` hold ``orch.root_state``; ``PlantNitrogenRuntime`` holds
    ``orch.plant_n_state``). A load must write into those objects: rebinding
    the orchestrator attribute leaves the runtimes advancing a stale copy,
    which froze root depth and restarted uptake from a 5 cm root.
    """
    for f in fields(source):
        setattr(target, f.name, getattr(source, f.name))


class Patch:
    """A sub-field zone with its own orchestrator."""

    def __init__(self, config: PatchConfig) -> None:
        self.config = config
        # Per-patch harvested yield, captured before the crop is cleared so the
        # harvest report retains the per-patch/GYGA breakdown (#341). ``None``
        # means the patch has not been harvested this season.
        self.harvested_grain_g_m2: float | None = None
        self.harvested_crop_key: str | None = None
        crops = load_crop_presets(Path("data/crops/presets.yaml"))
        climates = load_climate_presets(Path("data/climate/presets.yaml"))
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))

        profile = soil_lib.soils[config.soil_profile_key]
        # A harvested (or never-planted) patch has an empty crop_key; it holds no
        # standing crop, so the orchestrator is built bare (fallow, #542). This
        # lets a mid-stagger save with some patches already harvested round-trip
        # through load without a missing-preset lookup (#371).
        crop = (
            crops.get_preset(config.crop_key, config.climate_key)
            if config.crop_key
            else None
        )
        climate = climates.climates[config.climate_key]

        self.orch = FullSimulationOrchestrator(
            profile,
            crop=crop,
            latitude_deg=climate.latitude_deg,
            fallow=not config.crop_key,
        )
        self.recorder = EventRecorder(self.orch.event_bus)

    def step_day(self, drivers: DailyDrivers, **kwargs: Any) -> None:
        self.orch.step_day(drivers=drivers, **kwargs)

    def reset_crop(self, preset: CropPreset | None) -> None:
        """Reset this patch to a new crop and re-wire its event recorder.

        ``orch.reset_crop`` calls ``event_bus.clear()``, which drops every
        subscription — including the recorder created in ``__init__``. Without
        rebuilding it, events emitted in the next season go unrecorded, so
        ``/step`` returns empty ``daily_snapshots``/events from season 2 onward
        (#402). Replacing the recorder (rather than re-subscribing the old one)
        guarantees exactly one live subscription and no double-recording.

        ``preset=None`` leaves the patch bare: a fallow orchestrator and
        ``crop_key == ""``, so a save reloads it bare (#542). A preset sets
        ``crop_key`` to the preset's key, so a save reloads it planted.
        """
        self.orch.reset_crop(preset, fallow=preset is None)
        crop_key = "" if preset is None else preset.key or self.config.crop_key
        self.config = replace(self.config, crop_key=crop_key)
        self.recorder = EventRecorder(self.orch.event_bus)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this patch's config, soil, plant and management state.

        ``runtime_memory`` (optional within schema v1, #577) carries the
        cross-day memory the runtimes, cycles and orchestrator hold outside
        every ``*State`` container (``runtime_memory_to_dict``), so that a load
        continues the saved run exactly.
        """
        orch = self.orch
        return {
            "config": {
                "soil_profile_key": self.config.soil_profile_key,
                "crop_key": self.config.crop_key,
                "climate_key": self.config.climate_key,
                "area_fraction": self.config.area_fraction,
            },
            "soil_snapshot": orch.snapshot_soil().to_dict(),
            "canopy_state": orch.canopy.state.to_dict(),
            "phenology_state": orch.phenology.state.to_dict(),
            "root_state": orch.root_state.to_dict(),
            # Optional keys within schema v1 (#515), like #284/#285/#371.
            "plant_n_state": orch.plant_n_state.to_dict(),
            "management_plan": orch.management_plan.to_dict(),
            "day_counter": orch.day_counter,
            "harvested_grain_g_m2": self.harvested_grain_g_m2,
            "harvested_crop_key": self.harvested_crop_key,
            "runtime_memory": orch.runtime_memory_to_dict(),
        }

    def restore_state(self, data: dict[str, Any]) -> None:
        """Restore soil, plant and management state saved by :meth:`to_dict`.

        Plant state is written into the live objects (see ``_copy_fields``).
        Keys added in #515 are optional: a pre-#515 save leaves the shoot-N
        stock, plan and day counter at their fresh-patch values. A fallow
        patch keeps its zero plant state, discarding the phantom plant a
        pre-#542 save carries. ``runtime_memory`` (#577) is applied last, in
        place; a save without it starts that memory fresh.
        """
        orch = self.orch
        orch.restore_soil(SoilSnapshot.from_dict(data["soil_snapshot"]))
        if not orch.is_fallow:
            self._restore_plant_state(data)
        if data.get("management_plan") is not None:
            orch.management_plan = ManagementPlan.from_dict(data["management_plan"])
        orch.day_counter = int(data.get("day_counter", 0))
        grain = data.get("harvested_grain_g_m2")
        self.harvested_grain_g_m2 = None if grain is None else float(grain)
        self.harvested_crop_key = data.get("harvested_crop_key")
        if data.get("runtime_memory"):
            orch.restore_runtime_memory(data["runtime_memory"])

    def _restore_plant_state(self, data: dict[str, Any]) -> None:
        """Write saved canopy, phenology, root and shoot-N state (#515)."""
        orch = self.orch
        if data.get("canopy_state"):
            _copy_fields(orch.canopy.state, CanopyState.from_dict(data["canopy_state"]))
        if data.get("phenology_state"):
            phs = PhenologyState.from_dict(data["phenology_state"])
            _copy_fields(orch.phenology.state, phs)
            # Sync canopy module's stage tracking from restored phenology
            orch.canopy._current_stage = phs.stage
            orch.canopy._current_gdd = phs.accumulated_gdd
        if data.get("root_state"):
            _copy_fields(orch.root_state, RootState.from_dict(data["root_state"]))
        if data.get("plant_n_state"):
            restored_n = PlantNitrogenState.from_dict(data["plant_n_state"])
            _copy_fields(orch.plant_n_state, restored_n)

    def harvest(self) -> PatchResult:
        snap = self.orch.harvest()
        grain_g = self.orch.canopy.state.grain_biomass_g_m2
        return PatchResult(
            patch_idx=0,  # set by Field
            crop_key=self.config.crop_key,
            grain_g_m2=grain_g,
            grain_kg_ha=grain_g * 10.0,
            soil_snapshot=snap,
        )


class Field:
    """A collection of patches that together form one agricultural field."""

    def __init__(self, field_id: str, patches: list[PatchConfig]) -> None:
        total = sum(p.area_fraction for p in patches)
        if abs(total - 1.0) > AREA_FRACTION_SUM_TOLERANCE:
            raise ValueError(f"Patch area fractions must sum to 1.0, got {total:.3f}")
        self.field_id = field_id
        self.patches: list[Patch] = [Patch(cfg) for cfg in patches]
        self._configs = list(patches)

    def step_day(self, drivers: DailyDrivers, **kwargs: Any) -> None:
        for patch in self.patches:
            patch.step_day(drivers=drivers, **kwargs)

    def harvest(self) -> list[PatchResult]:
        results = []
        for i, patch in enumerate(self.patches):
            result = patch.harvest()
            results.append(
                PatchResult(
                    patch_idx=i,
                    crop_key=result.crop_key,
                    grain_g_m2=result.grain_g_m2,
                    grain_kg_ha=result.grain_kg_ha,
                    soil_snapshot=result.soil_snapshot,
                )
            )
        return results

    def apply_irrigation(self, amount_mm: float) -> None:
        """Apply irrigation to all patches (same depth in mm per unit area)."""
        for patch in self.patches:
            patch.orch.apply_irrigation(amount_mm)

    def apply_fertilizer(self, fert_type: str, amount_kg_ha: float) -> None:
        """Apply fertilizer to all patches (same rate per ha)."""
        for patch in self.patches:
            patch.orch.apply_fertilizer(fert_type, amount_kg_ha)


class FieldManager:
    """Manages N fields, each with M patches (ADR-002)."""

    def __init__(self) -> None:
        self.fields: dict[str, Field] = {}

    def add_field(self, field_id: str, patches: list[PatchConfig]) -> Field:
        if field_id in self.fields:
            raise ValueError(f"Field {field_id!r} already exists")
        f = Field(field_id, patches)
        self.fields[field_id] = f
        return f

    def remove_field(self, field_id: str) -> None:
        if field_id not in self.fields:
            raise KeyError(f"Field {field_id!r} not found")
        del self.fields[field_id]

    def step_day(self, drivers: DailyDrivers, **kwargs: Any) -> None:
        """Advance all fields by one day."""
        for f in self.fields.values():
            f.step_day(drivers=drivers, **kwargs)

    def harvest_field(self, field_id: str) -> list[PatchResult]:
        return self.fields[field_id].harvest()

    def apply_patch_action(
        self,
        field_id: str,
        patch_idx: int,
        action: str,
        **params: Any,
    ) -> None:
        """Apply an action to a specific patch."""
        f = self.fields[field_id]
        if not (0 <= patch_idx < len(f.patches)):
            raise IndexError(
                f"patch_idx {patch_idx} out of range " f"[0, {len(f.patches)})"
            )
        patch = f.patches[patch_idx]
        if action == "irrigate":
            patch.orch.apply_irrigation(params.get("amount_mm", 0.0))
        elif action == "fertilize":
            patch.orch.apply_fertilizer(
                params.get("type", "urea"),
                params.get("amount_kg_ha", 0.0),
            )
        else:
            raise ValueError(f"Unknown patch action {action!r}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize all fields for save/load."""
        return {
            "fields": {
                fid: {"patches": [p.to_dict() for p in f.patches]}
                for fid, f in self.fields.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldManager:
        """Restore from save data."""
        mgr = cls()
        for fid, fdata in data.get("fields", {}).items():
            patch_data = fdata.get("patches", [])
            configs = [
                PatchConfig(
                    soil_profile_key=pdata["config"]["soil_profile_key"],
                    crop_key=pdata["config"]["crop_key"],
                    climate_key=pdata["config"]["climate_key"],
                    area_fraction=float(pdata["config"]["area_fraction"]),
                )
                for pdata in patch_data
            ]
            field_obj = mgr.add_field(fid, configs)
            for patch, pdata in zip(field_obj.patches, patch_data, strict=True):
                patch.restore_state(pdata)
        return mgr
