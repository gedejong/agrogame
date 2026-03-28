"""Field→Patch→Orchestrator hierarchy (ADR-002, AGRO-108).

FieldManager manages N fields, each with M patches. Each patch wraps
a FullSimulationOrchestrator with its own soil profile, crop, and
EventBus. The simulation engine is unchanged — this is a game-layer
coordinator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator, SoilSnapshot
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.presets import load_climate_presets


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


class Patch:
    """A sub-field zone with its own orchestrator."""

    def __init__(self, config: PatchConfig) -> None:
        self.config = config
        crops = load_crop_presets(Path("data/crops/presets.yaml"))
        climates = load_climate_presets(Path("data/climate/presets.yaml"))
        soil_lib = load_soil_presets(Path("soils/presets.yaml"))

        profile = soil_lib.soils[config.soil_profile_key]
        crop = crops.get_preset(config.crop_key, config.climate_key)
        climate = climates.climates[config.climate_key]

        self.orch = FullSimulationOrchestrator(
            profile, crop=crop, latitude_deg=climate.latitude_deg
        )

    def step_day(self, drivers: DailyDrivers, **kwargs: Any) -> None:
        self.orch.step_day(drivers=drivers, **kwargs)

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
        if abs(total - 1.0) > 0.01:
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
        """Distribute irrigation across patches by area fraction."""
        for patch in self.patches:
            scaled = amount_mm * patch.config.area_fraction
            if scaled > 0:
                patch.orch.apply_irrigation(scaled)

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
                fid: {
                    "patches": [
                        {
                            "config": {
                                "soil_profile_key": p.config.soil_profile_key,
                                "crop_key": p.config.crop_key,
                                "climate_key": p.config.climate_key,
                                "area_fraction": p.config.area_fraction,
                            },
                            "soil_snapshot": p.orch.snapshot_soil().to_dict(),
                        }
                        for p in f.patches
                    ]
                }
                for fid, f in self.fields.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FieldManager:
        """Restore from save data."""
        mgr = cls()
        for fid, fdata in data.get("fields", {}).items():
            configs = []
            snapshots = []
            for pdata in fdata.get("patches", []):
                cfg = pdata["config"]
                configs.append(
                    PatchConfig(
                        soil_profile_key=cfg["soil_profile_key"],
                        crop_key=cfg["crop_key"],
                        climate_key=cfg["climate_key"],
                        area_fraction=float(cfg["area_fraction"]),
                    )
                )
                snapshots.append(SoilSnapshot.from_dict(pdata["soil_snapshot"]))
            field_obj = mgr.add_field(fid, configs)
            for i, snap in enumerate(snapshots):
                field_obj.patches[i].orch.restore_soil(snap)
        return mgr
