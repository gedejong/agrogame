shader_type spatial;
// Soil cutaway layer — PBR soil texture with water fill from bottom up.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform vec4 tint_color : source_color = vec4(1.0);
uniform float water_fill : hint_range(0.0, 1.0) = 0.0;
uniform float box_height : hint_range(0.01, 2.0) = 0.25;
uniform float emission_strength : hint_range(0.0, 1.0) = 0.15;
uniform float normal_strength : hint_range(0.0, 2.0) = 1.4;
uniform float detail_scale : hint_range(1.0, 8.0) = 2.5;

const vec3 WATER_COLOR = vec3(0.3, 0.55, 0.85);
const float EDGE_SOFT = 0.02;

varying float v_height_norm;

void vertex() {
	v_height_norm = (VERTEX.y / box_height) + 0.5;
}

void fragment() {
	vec3 soil = texture(albedo_texture, UV).rgb * tint_color.rgb;

	// Normal: base + tiled detail for visible grain/aggregate texture
	vec3 norm_base = texture(normal_texture, UV).rgb;
	vec3 norm_detail = texture(normal_texture, UV * detail_scale).rgb;
	vec3 norm_blend = normalize(
		vec3(norm_base.xy + (norm_detail.xy - 0.5) * 0.5, norm_base.z)
	);

	// Water fills from bottom up
	float wet = smoothstep(water_fill - EDGE_SOFT, water_fill + EDGE_SOFT, v_height_norm);
	float wetness = 1.0 - wet;
	vec3 color = mix(soil, soil * 0.6 + WATER_COLOR * 0.4, wetness);

	ALBEDO = color;
	NORMAL_MAP = norm_blend;
	NORMAL_MAP_DEPTH = normal_strength;
	ROUGHNESS = mix(0.9, 0.35, wetness);
	METALLIC = 0.0;
	SPECULAR = mix(0.15, 0.5, wetness);
	EMISSION = color * emission_strength;
}
