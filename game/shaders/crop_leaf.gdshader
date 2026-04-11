shader_type spatial;
render_mode cull_disabled;
// Shared crop leaf shader — alpha mask + senescence + per-type stress coloring.

uniform sampler2D alpha_mask : source_color;
uniform vec3 base_color : source_color = vec3(0.2, 0.55, 0.15);
uniform float senescence : hint_range(0.0, 1.0) = 0.0;
// Leaf vertical position: 0.0 = bottom, 1.0 = top of plant.
// Lower leaves senesce faster (bottom-up yellowing during grain fill).
uniform float leaf_height : hint_range(0.0, 1.0) = 0.5;

// Per-stress-type uniforms (continuous 0.0-1.0).
uniform float stress_water : hint_range(0.0, 1.0) = 0.0;
uniform float stress_n : hint_range(0.0, 1.0) = 0.0;
uniform float stress_p : hint_range(0.0, 1.0) = 0.0;
uniform float stress_fe : hint_range(0.0, 1.0) = 0.0;
uniform float stress_zn : hint_range(0.0, 1.0) = 0.0;

const vec3 GREEN = vec3(0.2, 0.55, 0.15);
const vec3 YOUNG_GREEN = vec3(0.35, 0.65, 0.25);
const vec3 SENESCENT = vec3(0.7, 0.6, 0.2);
const vec3 DEAD = vec3(0.5, 0.4, 0.2);

// Stress color targets
const vec3 DROUGHT_COLOR = vec3(0.35, 0.28, 0.15);  // dark brown — wilted
const vec3 N_DEFICIENCY = vec3(0.65, 0.70, 0.30);   // pale yellow-green — chlorosis
const vec3 P_DEFICIENCY = vec3(0.45, 0.20, 0.40);   // reddish-purple
const vec3 FE_CHLOROSIS = vec3(0.75, 0.72, 0.35);   // yellow — interveinal chlorosis blade
const vec3 FE_VEIN_COLOR = vec3(0.2, 0.55, 0.15);   // green veins stay green
const vec3 ZN_DEFICIENCY = vec3(0.55, 0.40, 0.22);  // bronze/brown stunting

void fragment() {
	float mask = texture(alpha_mask, UV).r;
	if (mask < 0.3) {
		discard;
	}

	// Bottom-up senescence: lower leaves (leaf_height~0) senesce faster.
	// Gradient adds up to 0.4 extra senescence at bottom, 0 at top.
	float effective_sen = clamp(senescence + (1.0 - leaf_height) * senescence * 0.4, 0.0, 1.0);

	// Base color from senescence
	vec3 color = mix(YOUNG_GREEN, base_color, smoothstep(0.0, 0.3, effective_sen + 0.5));
	color = mix(color, SENESCENT, smoothstep(0.0, 0.7, effective_sen));
	color = mix(color, DEAD, smoothstep(0.5, 1.0, effective_sen));

	// --- Per-type stress overlays (additive blending, clamped) ---

	// Drought: darken + brown, stronger at leaf margins (UV.y near 0 or 1)
	float edge = smoothstep(0.0, 0.3, abs(UV.y - 0.5));  // 1.0 at margins, 0.0 at midrib
	float drought_intensity = stress_water * (0.5 + edge * 0.5);
	color = mix(color, DROUGHT_COLOR, drought_intensity * 0.6);

	// Nitrogen deficiency: uniform pale yellow-green tint
	color = mix(color, N_DEFICIENCY, stress_n * 0.55);

	// Phosphorus deficiency: reddish-purple tint
	color = mix(color, P_DEFICIENCY, stress_p * 0.5);

	// Iron chlorosis: interveinal — veins stay green, blade yellows.
	// Procedural vein pattern using UV: parallel veins for monocots.
	// Ref: Yan & Hunt 1999 — simplified vein model for grasses.
	float vein_pattern = abs(sin(UV.y * 12.0));
	float is_vein = smoothstep(0.6, 0.9, vein_pattern);  // 1.0 on veins
	vec3 fe_color = mix(FE_CHLOROSIS, FE_VEIN_COLOR, is_vein);
	color = mix(color, fe_color, stress_fe * 0.55);

	// Zinc deficiency: bronze/brown stunting tint
	color = mix(color, ZN_DEFICIENCY, stress_zn * 0.5);

	// Waxy cuticle highlight
	float ndotv = abs(dot(NORMAL, VIEW));
	float sheen = pow(1.0 - ndotv, 3.0) * 0.15 + pow(ndotv, 6.0) * 0.1;
	color += vec3(sheen) * (1.0 - effective_sen);

	ALBEDO = color;
	ROUGHNESS = mix(0.5, 0.8, effective_sen);
	METALLIC = 0.0;
	ALPHA_SCISSOR_THRESHOLD = 0.3;
	ALPHA = mask;
}
