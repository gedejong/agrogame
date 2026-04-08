shader_type spatial;
render_mode cull_disabled;
// Soil tile shader — PBR with SOM/moisture darkening, detail normal tiling.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform float som_frac : hint_range(0.0, 1.0) = 0.0;
uniform float moisture_frac : hint_range(0.0, 1.0) = 0.0;
uniform float selected : hint_range(0.0, 1.0) = 0.0;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.2;
uniform float detail_scale : hint_range(1.0, 8.0) = 3.0;

const vec3 SOM_DARK = vec3(0.4, 0.3, 0.2);
const float SOM_STRENGTH = 0.7;
const vec3 MOISTURE_DARK = vec3(0.55, 0.55, 0.6);
const float MOISTURE_STRENGTH = 0.5;

void fragment() {
	vec4 albedo = texture(albedo_texture, UV);
	vec3 color = albedo.rgb;

	// SOM darkening: lerp toward brown
	color = mix(color, color * SOM_DARK, som_frac * SOM_STRENGTH);
	// Moisture darkening: lerp toward grey-blue
	color = mix(color, color * MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH);

	// Normal map: base + detail at higher frequency for micro-texture
	vec3 norm_base = texture(normal_texture, UV).rgb;
	vec3 norm_detail = texture(normal_texture, UV * detail_scale).rgb;
	// Blend: base dominates, detail adds fine grain
	vec3 norm_blend = normalize(
		vec3(norm_base.xy + (norm_detail.xy - 0.5) * 0.4, norm_base.z)
	);

	ALBEDO = color;
	NORMAL_MAP = norm_blend;
	NORMAL_MAP_DEPTH = normal_strength;
	ROUGHNESS = mix(0.85, 0.3, moisture_frac);
	METALLIC = 0.0;
	SPECULAR = mix(0.2, 0.5, moisture_frac);

	// Selection highlight: soft emission glow
	EMISSION = vec3(0.3, 0.5, 0.9) * selected * 0.4;
}
