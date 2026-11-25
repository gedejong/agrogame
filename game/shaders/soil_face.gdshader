shader_type spatial;
// A cut face of the diorama slab (#646, ADR-022 decision 1). Every number it
// draws comes from DioramaSlab and SoilFaceColour, where GUT pins it: per
// texel of profile_tex, R scales the texture class's cross-section texture to
// the layer's reflectance, G is the root density and B the class (column / 2).
// A simulated segment's profile_tex is one texel wide and runs down the
// section; the extension placeholder's is one texel per segment, one high.
#include "res://shaders/srgb.gdshaderinc"

uniform sampler2D profile_tex : filter_nearest, repeat_disable;
uniform sampler2D grain_sandy : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D grain_loam : source_color, filter_linear_mipmap, repeat_enable;
uniform sampler2D grain_clay : source_color, filter_linear_mipmap, repeat_enable;
// Emission over albedo: DioramaSlab.FACE_FILL on a face turned from the sun.
uniform float face_fill = 0.0;

// Style constants (#646): grain repeats and root strands per world unit, the
// strands' waviness, and the root trace colour (sRGB).
const float GRAIN_PER_WU = 1.5;
const float STRANDS_PER_WU = 14.0;
const float WAVES_PER_WU = 22.0;
const vec3 ROOT_COLOUR = SRGB_TO_LINEAR(vec3(0.86, 0.80, 0.66));

varying vec3 v_world;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float wave(float x) {
	float i = floor(x);
	float f = fract(x);
	f = f * f * (3.0 - 2.0 * f);
	return mix(hash(vec2(i, 0.0)), hash(vec2(i + 1.0, 0.0)), f);
}

void vertex() {
	v_world = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec4 prof = texture(profile_tex, UV);
	// x + z runs along both camera faces, so grain and strands turn the corner.
	float u = v_world.x + v_world.z;
	vec2 g_uv = vec2(u, -v_world.y) * GRAIN_PER_WU;
	vec3 sandy = texture(grain_sandy, g_uv).rgb;
	vec3 loam = texture(grain_loam, g_uv).rgb;
	vec3 clay = texture(grain_clay, g_uv).rgb;
	float k = prof.b * 2.0;
	vec3 col = min((k < 0.5 ? sandy : (k < 1.5 ? loam : clay)) * prof.r, vec3(1.0));
	// Root traces: wavy near-vertical strands; a strand shows where its random
	// rank falls under the density at that depth.
	float x = u * STRANDS_PER_WU;
	x += (wave(-v_world.y * WAVES_PER_WU + floor(x)) - 0.5) * 1.6;
	float line = 1.0 - smoothstep(0.05, 0.14, abs(fract(x) - 0.5));
	float on = step(hash(vec2(floor(x), 7.0)), prof.g) * step(1e-4, prof.g);
	col = mix(col, ROOT_COLOUR, line * on * 0.85);
	ALBEDO = col;
	EMISSION = col * face_fill;
	ROUGHNESS = 0.95;
	SPECULAR = 0.2;
}
