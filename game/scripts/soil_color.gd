extends RefCounted
## Pure color calculation for dynamic soil tile appearance.
## Three modes: NATURAL (subtle darkening preserving texture), SOM heatmap,
## and MOISTURE heatmap for diagnostic overlays.

## Overlay display modes
enum Mode { NATURAL, SOM_HEATMAP, MOISTURE_HEATMAP }

## Reference SOM range for normalization (g C/m² across all layers).
## 0 = bare/no-data, ~5000 = very rich (>5% OM).
const SOM_MIN_C_G_M2 := 0.0
const SOM_MAX_C_G_M2 := 5000.0

## Saturated volumetric water content (m³/m³, approximate upper bound).
const THETA_SATURATED := 0.45

## SOM darkening target: rich dark brown applied as modulate.
const SOM_DARK := Color(0.4, 0.3, 0.2)

## Moisture darkening: multiply toward this shade when wet.
const MOISTURE_DARK := Color(0.55, 0.55, 0.6)

## Maximum SOM darkening + saturation strength (0 = no effect, 1 = full).
const SOM_STRENGTH := 0.7

## Maximum moisture darkening strength.
const MOISTURE_STRENGTH := 0.5

## SOM heatmap stops: red (degraded) → yellow → green (rich)
const _SOM_HEATMAP_LOW := Color(0.85, 0.25, 0.15)
const _SOM_HEATMAP_MID := Color(0.95, 0.85, 0.2)
const _SOM_HEATMAP_HIGH := Color(0.2, 0.75, 0.25)

## Moisture heatmap stops: brown (dry) → cyan → blue (saturated)
const _MOISTURE_HEATMAP_LOW := Color(0.8, 0.65, 0.35)
const _MOISTURE_HEATMAP_MID := Color(0.3, 0.75, 0.8)
const _MOISTURE_HEATMAP_HIGH := Color(0.15, 0.3, 0.85)


static func calculate(
	som_total_c_g_m2: float, theta_surface: float, mode: int = Mode.NATURAL
) -> Color:
	match mode:
		Mode.SOM_HEATMAP:
			return _som_heatmap(som_total_c_g_m2)
		Mode.MOISTURE_HEATMAP:
			return _moisture_heatmap(theta_surface)
		_:
			return _natural(som_total_c_g_m2, theta_surface)


static func _natural(som_total_c_g_m2: float, theta_surface: float) -> Color:
	## Modulate color: White = no change; darker = more SOM/moisture.
	## Higher SOM also boosts saturation for richer appearance.
	var base := Color.WHITE

	var som_frac := clampf(
		som_total_c_g_m2 / SOM_MAX_C_G_M2,
		0.0,
		1.0,
	)
	# Darken toward rich brown
	var som_color := base.lerp(SOM_DARK, som_frac * SOM_STRENGTH)
	# Boost saturation for rich soil (desaturate degraded soil)
	som_color.s = som_color.s + som_frac * 0.3

	var moisture_frac := clampf(theta_surface / THETA_SATURATED, 0.0, 1.0)
	var final_color := som_color.lerp(MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH)

	return final_color


static func _som_heatmap(som_total_c_g_m2: float) -> Color:
	## Red (low/degraded) → yellow (moderate) → green (rich).
	var frac := clampf(som_total_c_g_m2 / SOM_MAX_C_G_M2, 0.0, 1.0)
	if frac < 0.5:
		return _SOM_HEATMAP_LOW.lerp(_SOM_HEATMAP_MID, frac * 2.0)
	return _SOM_HEATMAP_MID.lerp(_SOM_HEATMAP_HIGH, (frac - 0.5) * 2.0)


static func _moisture_heatmap(theta_surface: float) -> Color:
	## Brown (dry) → cyan (moist) → blue (saturated).
	var frac := clampf(theta_surface / THETA_SATURATED, 0.0, 1.0)
	if frac < 0.5:
		return _MOISTURE_HEATMAP_LOW.lerp(_MOISTURE_HEATMAP_MID, frac * 2.0)
	return _MOISTURE_HEATMAP_MID.lerp(_MOISTURE_HEATMAP_HIGH, (frac - 0.5) * 2.0)
