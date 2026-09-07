shader_type spatial;
render_mode cull_disabled;
// Shared crop leaf shader — alpha mask + senescence + per-type stress coloring.
// Stress symptoms follow plant physiology:
//   Mobile nutrients (N, P) → older/lower leaves first
//   Immobile nutrients (Fe, Zn) → younger/upper leaves first
// Ref: Marschner 2012, Mineral Nutrition of Higher Plants.
#include "res://shaders/crop_wind.gdshaderinc"

uniform sampler2D alpha_mask : source_color;
uniform vec3 base_color : source_color = vec3(0.2, 0.55, 0.15);
uniform float senescence : hint_range(0.0, 1.0) = 0.0;
// Leaf vertical position: 0.0 = bottom/older, 1.0 = top/younger.
uniform float leaf_height : hint_range(0.0, 1.0) = 0.5;
// Leaf expansion: 0.0 = just emerged (pale young green), 1.0 = fully expanded.
uniform float age : hint_range(0.0, 1.0) = 1.0;
// Strength of the pale midrib along UV.y = 0.5 and of the parallel veins
// beside it; zero for leaves without a single central rib.
uniform float midrib : hint_range(0.0, 1.0) = 0.0;

// Wind: the whole-plant bend and the free-end sway come from the shared
// include; the blade runs from its attachment (UV.x = 0, the collar) to the
// tip, or, for a leaf hanging from a petiole, from UV.y = 0 down to the lobes.
uniform float hanging : hint_range(0.0, 1.0) = 0.0;

// Per-stress-type uniforms (continuous 0.0-1.0).
uniform float stress_water : hint_range(0.0, 1.0) = 0.0;
uniform float stress_n : hint_range(0.0, 1.0) = 0.0;
uniform float stress_p : hint_range(0.0, 1.0) = 0.0;
uniform float stress_fe : hint_range(0.0, 1.0) = 0.0;
uniform float stress_zn : hint_range(0.0, 1.0) = 0.0;
// Transient damage from FrostDamageApplied / HeatDamageApplied events.
uniform float stress_frost : hint_range(0.0, 1.0) = 0.0;
uniform float stress_heat : hint_range(0.0, 1.0) = 0.0;

const vec3 GREEN = vec3(0.2, 0.55, 0.15);
const vec3 YOUNG_GREEN = vec3(0.35, 0.65, 0.25);
const vec3 SENESCENT = vec3(0.7, 0.6, 0.2);
const vec3 DEAD = vec3(0.5, 0.4, 0.2);

// Stress color targets
const vec3 DROUGHT_COLOR = vec3(0.35, 0.28, 0.15);    // dark brown — wilted
const vec3 N_DEFICIENCY = vec3(0.70, 0.72, 0.30);     // pale yellow-green — uniform chlorosis
const vec3 P_DARK_GREEN = vec3(0.12, 0.35, 0.10);     // abnormally dark green (P-starved)
const vec3 P_PURPLE = vec3(0.40, 0.15, 0.35);         // purple/reddish anthocyanin
const vec3 FE_CHLOROSIS = vec3(0.82, 0.80, 0.45);     // strong yellow — almost white in severe
const vec3 FE_VEIN_COLOR = vec3(0.2, 0.55, 0.15);     // green veins stay green
const vec3 ZN_PALE = vec3(0.70, 0.65, 0.40);          // pale band color
const vec3 ZN_BRONZE = vec3(0.50, 0.38, 0.20);        // bronze/necrotic band
const vec3 FROST_NECROSIS = vec3(0.10, 0.08, 0.06);   // near-black, water-soaked tissue
const vec3 HEAT_BURN = vec3(0.55, 0.30, 0.10);        // brown scorch — leaf tip burn

void vertex() {
	if (wind_strength > 0.001) {
		vec3 v = VERTEX;
		WindFrame f = wind_frame(MODEL_MATRIX, TIME, INSTANCE_CUSTOM.r);
		// The attachment stays put; the free end flutters, more the further out.
		float reach = mix(UV.x, UV.y, hanging);
		VERTEX += wind_plant_bend(f, v) + wind_leaf_sway(f, length(v), reach);
	}
}

void fragment() {
	float mask = texture(alpha_mask, UV).r;
	if (mask < 0.3) {
		discard;
	}
	// A blade is a two-sided sheet: shade whichever face is towards the viewer.
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}

	// Bottom-up senescence: lower leaves senesce faster during grain fill.
	float effective_sen = clamp(senescence + (1.0 - leaf_height) * senescence * 0.4, 0.0, 1.0);

	// Young, still-expanding leaves are a paler green than mature blades.
	vec3 color = mix(YOUNG_GREEN, base_color, age);
	// Midrib: a pale ridge along the blade centre, with faint parallel veins.
	float rib = 1.0 - smoothstep(0.0, 0.05, abs(UV.y - 0.5));
	float veins = 0.5 + 0.5 * sin(UV.y * 75.0);
	color *= 1.0 - midrib * 0.07 * veins;
	color = mix(color, color * 1.3 + vec3(0.08, 0.08, 0.02), rib * midrib * 0.8);
	color = mix(color, SENESCENT, smoothstep(0.0, 0.7, effective_sen));
	color = mix(color, DEAD, smoothstep(0.5, 1.0, effective_sen));

	// --- Per-type stress overlays ---
	// Leaf position factor: 0=bottom/old, 1=top/young
	float old_leaf = 1.0 - leaf_height;  // stronger on older/lower leaves
	float young_leaf = leaf_height;       // stronger on younger/upper leaves

	// DROUGHT: brown edges + darkening. Affects all leaves, worse on older.
	float edge = smoothstep(0.0, 0.3, abs(UV.y - 0.5));
	float drought_f = stress_water * (0.5 + edge * 0.5) * (0.6 + old_leaf * 0.4);
	color = mix(color, DROUGHT_COLOR, drought_f * 0.6);

	// NITROGEN: uniform pale yellow-green. Mobile → older leaves first.
	// Ref: whole leaf turns pale, starting from tip of lower leaves.
	float n_tip = smoothstep(0.3, 0.8, UV.x);  // stronger toward leaf tip
	float n_f = stress_n * (0.4 + old_leaf * 0.6) * (0.7 + n_tip * 0.3);
	color = mix(color, N_DEFICIENCY, n_f * 0.6);

	// PHOSPHORUS: dark green base + purple overlay. Mobile → older leaves.
	// Ref: anthocyanin accumulation, dark green because N accumulates.
	float p_f = stress_p * (0.4 + old_leaf * 0.6);
	color = mix(color, P_DARK_GREEN, p_f * 0.3);  // darken first
	color = mix(color, P_PURPLE, p_f * 0.4);       // then purple tint

	// IRON: interveinal chlorosis on YOUNG leaves. Immobile → top first.
	// Ref: veins green, blade yellow to almost white. Parallel veins (monocot).
	float vein_pattern = abs(sin(UV.y * 12.0));
	float is_vein = smoothstep(0.55, 0.85, vein_pattern);
	vec3 fe_color = mix(FE_CHLOROSIS, FE_VEIN_COLOR, is_vein);
	float fe_f = stress_fe * (0.3 + young_leaf * 0.7);  // top leaves first
	color = mix(color, fe_color, fe_f * 0.6);

	// ZINC: banded pale/bronze stripes. Immobile → young leaves first.
	// Ref: light bands across leaf + shortened internodes.
	float zn_band = abs(sin(UV.x * 8.0));  // bands along leaf length
	float is_pale_band = smoothstep(0.4, 0.7, zn_band);
	vec3 zn_color = mix(ZN_BRONZE, ZN_PALE, is_pale_band);
	float zn_f = stress_zn * (0.3 + young_leaf * 0.7);  // top leaves first
	color = mix(color, zn_color, zn_f * 0.55);

	// FROST: patchy near-black necrosis. Sudden — affects all leaves.
	// Ref: ice crystal damage causes water-soaked, then blackened tissue.
	// Procedural noise via UV + wind_phase gives per-leaf pattern variation.
	float frost_noise = sin(UV.x * 17.3 + UV.y * 23.1 + wind_phase) *
	                    sin(UV.x * 9.7 - UV.y * 13.5 + wind_phase * 1.7);
	float frost_patch = smoothstep(-0.2, 0.6, frost_noise);
	float frost_f = stress_frost * (0.4 + frost_patch * 0.6);
	color = mix(color, FROST_NECROSIS, frost_f * 0.85);

	// HEAT: leaf tip burn — brown scorch on outer 35% of leaf.
	// Ref: high transpiration + low water → tip desiccation first.
	// Stronger on younger/upper leaves (higher VPD exposure at canopy top).
	float heat_tip = smoothstep(0.65, 1.0, UV.x);
	float heat_f = stress_heat * heat_tip * (0.5 + young_leaf * 0.5);
	color = mix(color, HEAT_BURN, heat_f * 0.8);

	// Waxy cuticle highlight
	float ndotv = abs(dot(NORMAL, VIEW));
	float sheen = pow(1.0 - ndotv, 3.0) * 0.15 + pow(ndotv, 6.0) * 0.1;
	color += vec3(sheen) * (1.0 - effective_sen);

	ALBEDO = color;
	// Thin tissue transmits light: a blade between viewer and sun glows.
	BACKLIGHT = color * 0.4 * (1.0 - effective_sen * 0.5);
	ROUGHNESS = mix(0.5, 0.8, effective_sen);
	METALLIC = 0.0;
	ALPHA_SCISSOR_THRESHOLD = 0.3;
	ALPHA = mask;
}
