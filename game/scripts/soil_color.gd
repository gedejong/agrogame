extends RefCounted
## Pure color calculation for dynamic soil tile appearance.
## SOM content darkens toward rich brown; moisture darkens further.
## Base texture hue (sandy warm, clay cool) is preserved via modulation.

## Reference SOM range for normalization (g C/m² across all layers).
## 0 = bare/no-data, ~5000 = very rich (>5% OM). Linear scale from 0
## so even very degraded soils get slight modulation.
const SOM_MIN_C_G_M2 := 0.0
const SOM_MAX_C_G_M2 := 5000.0

## Saturated volumetric water content (approximate upper bound).
const THETA_SATURATED := 0.45

## SOM darkening target: rich dark brown applied as modulate.
const SOM_DARK := Color(0.55, 0.45, 0.35)

## Moisture darkening: multiply toward this shade when wet.
const MOISTURE_DARK := Color(0.7, 0.7, 0.7)

## Maximum SOM darkening strength (0 = no effect, 1 = full blend).
const SOM_STRENGTH := 0.4

## Maximum moisture darkening strength.
const MOISTURE_STRENGTH := 0.25


static func calculate(som_total_c_g_m2: float, theta_surface: float) -> Color:
	## Returns a modulate color to apply on top of the base tile texture.
	## White (1,1,1) = no change; darker = more SOM/moisture.
	var base := Color.WHITE

	# SOM darkening: higher SOM = darker tile
	var som_frac := clampf(
		(som_total_c_g_m2 - SOM_MIN_C_G_M2) / (SOM_MAX_C_G_M2 - SOM_MIN_C_G_M2),
		0.0,
		1.0,
	)
	var som_color := base.lerp(SOM_DARK, som_frac * SOM_STRENGTH)

	# Moisture darkening: wetter = darker
	var moisture_frac := clampf(theta_surface / THETA_SATURATED, 0.0, 1.0)
	var final_color := som_color.lerp(MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH)

	return final_color
