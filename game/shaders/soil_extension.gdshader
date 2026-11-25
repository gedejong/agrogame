shader_type spatial;
// The diorama slab's decorative extension below the simulated profile (#652,
// ADR-022 decision 1). It reads no simulation value: DioramaRegions fills in a
// climate key's layer stack and DioramaArtefacts its stones, gravel lenses and
// old roots, where GUT pins every number. Lengths are metres along the unfolded
// face (u, left to right across both camera faces) and below the surface (d).
// Slots 0 to 3 are the layers top down, slot 4 the artefact set; each set
// repeats at its real-world size, with its OpenGL normal map and its ARM map.

uniform sampler2D set_diff[5] : source_color, filter_linear_mipmap_anisotropic, repeat_enable;
// Linear without hint_normal, which uniform arrays do not take; NORMAL_MAP
// rebuilds z from x and y, as for the RGTC import (compress/normal_map=1).
uniform sampler2D set_nor_gl[5] : filter_linear_mipmap_anisotropic, repeat_enable;
uniform sampler2D set_arm[5] : filter_linear_mipmap_anisotropic, repeat_enable;
uniform float set_size_m[5];
uniform float layer_bottom_m[3];
uniform float wu_per_m = 0.5;
uniform float profile_bottom_m = 1.0;
// Per artefact, row 0: centre u, centre d, half width, half height (m);
// row 1: kind (0 corestone, 1 gravel lens, 2 old root), a phase in [0, 1) and,
// for a corestone, its blockiness (0 oval to 1 rounded block).
uniform sampler2D artefacts : filter_nearest, repeat_disable;
uniform int artefact_count = 0;
// Emission over albedo from DioramaSlab._fill(): per quad, since the +x and +z
// quads share this material but only the one turned from the sun is filled.
instance uniform float face_fill = 0.0;

// Style constants (#652 refinement): layer boundaries wave by at most 5 cm and
// blend over 4 cm; old roots wiggle by 3 cm; the seam marks the profile bottom.
const float WAVE_M = 0.05;
const float WAVES_PER_M = 1.3;
const float BLEND_M = 0.02;
const float ROOT_WIGGLE_M = 0.03;
// How far a corestone's normal tilts outward towards its rim: rounded relief.
const float DOME = 0.25;
const vec3 ROOT_COLOUR = vec3(0.025, 0.018, 0.012);  // linear, a dark organic fill
const float SEAM_M = 0.015;

varying vec3 v_world;

float hash(float x) {
	return fract(sin(x * 127.1) * 43758.5453);
}

// Smooth 1D value noise in [-1, 1].
float vnoise(float x) {
	float i = floor(x);
	float f = fract(x);
	return mix(hash(i), hash(i + 1.0), f * f * (3.0 - 2.0 * f)) * 2.0 - 1.0;
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	// x - z unfolds the +z face (x rising) and the +x face (z falling) into one
	// strip that runs left to right on screen and joins at the front corner.
	vec2 p = vec2(v_world.x - v_world.z, -v_world.y) / wu_per_m;
	float px = fwidth(p.x);
	vec3 alb = vec3(0.0);
	vec3 nor = vec3(0.0);
	vec3 arm = vec3(0.0);
	float above = 1.0;  // the share of this fragment below the previous boundary
	for (int i = 0; i < 4; i++) {
		float below = 0.0;
		if (i < 3) {
			float wave = 0.7 * vnoise(p.x * WAVES_PER_M + float(i) * 17.0);
			wave += 0.3 * vnoise(p.x * WAVES_PER_M * 4.0 + float(i) * 5.0);
			below = smoothstep(-BLEND_M, BLEND_M, p.y - layer_bottom_m[i] - WAVE_M * wave);
		}
		vec2 uv = p / set_size_m[i];
		float w = above - below;
		alb += w * texture(set_diff[i], uv).rgb;
		nor += w * texture(set_nor_gl[i], uv).rgb;
		arm += w * texture(set_arm[i], uv).rgb;
		above = below;
	}
	vec2 a_uv = p / set_size_m[4];
	vec3 a_alb = texture(set_diff[4], a_uv).rgb;
	vec3 a_nor = texture(set_nor_gl[4], a_uv).rgb;
	vec3 a_arm = texture(set_arm[4], a_uv).rgb;
	float body = 0.0;  // inside a corestone or a lens
	float rim = 0.0;  // a corestone's darker weathering rind
	float root = 0.0;
	vec2 dome = vec2(0.0);
	for (int i = 0; i < artefact_count; i++) {
		vec4 box = texelFetch(artefacts, ivec2(i, 0), 0);
		vec3 info = texelFetch(artefacts, ivec2(i, 1), 0).rgb;
		vec2 q = (p - box.xy) / box.zw;
		float aa = px / box.z;
		if (info.x < 0.5) {
			// A superellipse from oval (n = 2) to rounded joint block (n = 4),
			// with a lumpy outline.
			float n = mix(2.0, 4.0, info.z);
			float r = pow(pow(abs(q.x), n) + pow(abs(q.y), n), 1.0 / n);
			r += 0.06 * vnoise(atan(q.y, q.x) * 2.0 + info.y * 60.0);
			float inside = 1.0 - smoothstep(1.0 - aa, 1.0 + aa, r);
			body = max(body, inside);
			rim = max(rim, inside * smoothstep(0.75, 1.0, r));
			dome += inside * q * smoothstep(0.2, 1.0, r);
		} else if (info.x < 1.5) {
			// Biconvex: thickest at the middle, pinching out at both ends.
			float half_t = max(1.0 - q.x * q.x, 0.0);
			body = max(body, 1.0 - smoothstep(half_t - aa, half_t + aa, abs(q.y)));
		} else {
			// An old root: a dark, wavy trace at least 1.5 px wide, from its top
			// (q.y = -1), fading out over its lower half to none at its tip.
			float dx = abs(p.x - box.x - ROOT_WIGGLE_M * vnoise(p.y * 9.0 + info.y * 40.0));
			float half_w = max(box.z, px * 0.75);
			float line = 1.0 - smoothstep(half_w - px * 0.5, half_w + px * 0.5, dx);
			root = max(root, line * step(-1.0, q.y) * smoothstep(1.0, 0.0, q.y));
		}
	}
	alb = mix(alb, a_alb * (1.0 - 0.35 * rim), body);
	nor = mix(nor, a_nor, body);
	nor.xy += vec2(dome.x, -dome.y) * DOME;  // OpenGL convention: +y is up
	arm = mix(arm, a_arm, body);
	alb = mix(alb, ROOT_COLOUR, root * 0.9);
	alb *= 1.0 - 0.4 * (1.0 - smoothstep(0.0, SEAM_M, p.y - profile_bottom_m));
	ALBEDO = alb;
	NORMAL_MAP = nor;
	AO = arm.r;
	ROUGHNESS = arm.g;
	METALLIC = arm.b;
	EMISSION = alb * face_fill;
}
