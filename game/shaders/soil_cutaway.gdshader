shader_type spatial;
// Soil cutaway layer — blends soil texture with water from bottom up.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform vec4 tint_color : source_color = vec4(1.0);
uniform float water_fill : hint_range(0.0, 1.0) = 0.0;
uniform float box_height : hint_range(0.01, 2.0) = 0.25;
uniform float emission_strength : hint_range(0.0, 1.0) = 0.15;

const vec3 WATER_COLOR = vec3(0.3, 0.55, 0.85);
const float EDGE_SOFT = 0.02;

varying float v_height_norm;

void vertex() {
	// Normalize vertex Y to [0, 1]: 0 = bottom, 1 = top.
	// BoxMesh is centered, so VERTEX.y ranges [-h/2, +h/2].
	v_height_norm = (VERTEX.y / box_height) + 0.5;
}

void fragment() {
	vec3 soil = texture(albedo_texture, UV).rgb * tint_color.rgb;
	vec3 norm = texture(normal_texture, UV).rgb;

	// Water fills from bottom (v_height_norm=0) up to water_fill.
	float wet = smoothstep(water_fill - EDGE_SOFT, water_fill + EDGE_SOFT, v_height_norm);
	// wet=0 means below water line (wet), wet=1 means above (dry).
	float wetness = 1.0 - wet;

	vec3 color = mix(soil, soil * 0.65 + WATER_COLOR * 0.35, wetness);

	ALBEDO = color;
	NORMAL_MAP = norm;
	ROUGHNESS = mix(0.9, 0.5, wetness);
	METALLIC = 0.0;
	EMISSION = color * emission_strength;
}
