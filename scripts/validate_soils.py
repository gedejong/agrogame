from __future__ import annotations

from pathlib import Path

from agrogame.soil.loader import load_soil_presets


# Very light reference ranges (heuristic) inspired by common soil property ranges
FC_RANGE: tuple[float, float] = (0.05, 0.60)
WP_RANGE: tuple[float, float] = (0.02, 0.35)
SAT_RANGE: tuple[float, float] = (0.25, 0.85)
BD_RANGE: tuple[float, float] = (0.2, 2.0)  # g/cm3, peat to compacted clays
KSAT_RANGE: tuple[float, float] = (0.5, 200.0)  # mm/h


def main() -> int:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    violations = []
    for soil_id, profile in lib.soils.items():
        if len(profile.layers) < 3:
            violations.append((soil_id, "layers", f"<3 layers ({len(profile.layers)})"))
        total_depth = sum(layer.depth_cm for layer in profile.layers)
        if total_depth < 100:
            violations.append((soil_id, "depth_cm", f"total depth {total_depth} < 100"))
        for idx, layer in enumerate(profile.layers):
            if not (FC_RANGE[0] <= layer.field_capacity <= FC_RANGE[1]):
                violations.append(
                    (soil_id, f"layer[{idx}].field_capacity", layer.field_capacity)
                )
            if not (WP_RANGE[0] <= layer.wilting_point <= WP_RANGE[1]):
                violations.append(
                    (soil_id, f"layer[{idx}].wilting_point", layer.wilting_point)
                )
            if not (SAT_RANGE[0] <= layer.saturation <= SAT_RANGE[1]):
                violations.append(
                    (soil_id, f"layer[{idx}].saturation", layer.saturation)
                )
            if not (BD_RANGE[0] <= layer.bulk_density_g_cm3 <= BD_RANGE[1]):
                violations.append(
                    (
                        soil_id,
                        f"layer[{idx}].bulk_density_g_cm3",
                        layer.bulk_density_g_cm3,
                    )
                )
            if not (KSAT_RANGE[0] <= layer.ksat_mm_per_hour <= KSAT_RANGE[1]):
                violations.append(
                    (soil_id, f"layer[{idx}].ksat_mm_per_hour", layer.ksat_mm_per_hour)
                )

    if violations:
        print("Validation violations:")
        for v in violations:
            print(" -", v)
        return 1
    print("Soil presets validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
