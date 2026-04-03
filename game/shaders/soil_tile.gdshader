shader_type spatial;
// Soil tile shader — PBR base with SOM/moisture darkening.
// Replicates soil_color.gd natural mode logic in GPU.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform float som_frac : hint_range(0.0, 1.0) = 0.0;
uniform float moisture_frac : hint_range(0.0, 1.0) = 0.0;
uniform float selected : hint_range(0.0, 1.0) = 0.0;

// SOM darkening target: rich dark brown (matches SoilColor.SOM_DARK)
const vec3 SOM_DARK = vec3(0.4, 0.3, 0.2);
const float SOM_STRENGTH = 0.7;
// Moisture darkening target (matches SoilColor.MOISTURE_DARK)
const vec3 MOISTURE_DARK = vec3(0.55, 0.55, 0.6);
const float MOISTURE_STRENGTH = 0.5;

void fragment() {
	vec4 albedo = texture(albedo_texture, UV);
	vec3 color = albedo.rgb;

	// SOM darkening: lerp toward brown
	color = mix(color, color * SOM_DARK, som_frac * SOM_STRENGTH);

	// Moisture darkening: lerp toward grey-blue
	color = mix(color, color * MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH);

	ALBEDO = color;
	NORMAL_MAP = texture(normal_texture, UV).rgb;
	ROUGHNESS = 0.85;
	METALLIC = 0.0;

	// Selection highlight: soft emission glow
	EMISSION = vec3(0.3, 0.5, 0.9) * selected * 0.4;
}
