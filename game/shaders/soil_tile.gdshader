shader_type spatial;
render_mode cull_disabled;
// Soil tile — PBR with tiled texture for visible grain and depth.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform float som_frac : hint_range(0.0, 1.0) = 0.0;
uniform float moisture_frac : hint_range(0.0, 1.0) = 0.0;
uniform float selected : hint_range(0.0, 1.0) = 0.0;

// Texture tiling: base (macro pattern) + detail (micro grain)
const float BASE_TILE = 2.0;
const float DETAIL_TILE = 6.0;
const float NORMAL_STRENGTH = 1.5;
const float DETAIL_BLEND = 0.35;

const vec3 SOM_DARK = vec3(0.4, 0.3, 0.2);
const float SOM_STRENGTH = 0.7;
const vec3 MOISTURE_DARK = vec3(0.55, 0.55, 0.6);
const float MOISTURE_STRENGTH = 0.5;

void fragment() {
	// Tiled albedo: base for macro color + detail for grain
	vec2 uv_base = UV * BASE_TILE;
	vec2 uv_detail = UV * DETAIL_TILE;
	vec3 color_base = texture(albedo_texture, uv_base).rgb;
	vec3 color_detail = texture(albedo_texture, uv_detail).rgb;
	// Overlay blend: detail modulates base for visible grain without tiling seams
	vec3 color = color_base * (1.0 - DETAIL_BLEND) + color_base * color_detail * DETAIL_BLEND * 2.0;

	// SOM darkening
	color = mix(color, color * SOM_DARK, som_frac * SOM_STRENGTH);
	// Moisture darkening
	color = mix(color, color * MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH);

	// Normal: blend base + detail for multi-scale bumps
	vec3 norm_base = texture(normal_texture, uv_base).rgb;
	vec3 norm_detail = texture(normal_texture, uv_detail).rgb;
	vec3 norm = normalize(
		vec3(norm_base.xy + (norm_detail.xy - 0.5) * 0.5, norm_base.z)
	);

	ALBEDO = color;
	NORMAL_MAP = norm;
	NORMAL_MAP_DEPTH = NORMAL_STRENGTH;
	ROUGHNESS = mix(0.85, 0.3, moisture_frac);
	METALLIC = 0.0;
	SPECULAR = mix(0.2, 0.5, moisture_frac);
	EMISSION = vec3(0.3, 0.5, 0.9) * selected * 0.4;
}
