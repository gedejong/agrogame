shader_type spatial;
// Soil cutaway layer — tiled PBR texture with water fill from bottom up.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform vec4 tint_color : source_color = vec4(1.0);
uniform float water_fill : hint_range(0.0, 1.0) = 0.0;
uniform float box_height : hint_range(0.01, 2.0) = 0.25;
uniform float emission_strength : hint_range(0.0, 1.0) = 0.15;

const float BASE_TILE = 2.0;
const float DETAIL_TILE = 5.0;
const float NORMAL_STRENGTH = 1.6;
const vec3 WATER_COLOR = vec3(0.3, 0.55, 0.85);
const float EDGE_SOFT = 0.02;

varying float v_height_norm;

void vertex() {
	v_height_norm = (VERTEX.y / box_height) + 0.5;
}

void fragment() {
	vec2 uv_base = UV * BASE_TILE;
	vec2 uv_detail = UV * DETAIL_TILE;

	// Tiled albedo with grain overlay
	vec3 soil_base = texture(albedo_texture, uv_base).rgb * tint_color.rgb;
	vec3 soil_detail = texture(albedo_texture, uv_detail).rgb;
	vec3 soil = soil_base * 0.7 + soil_base * soil_detail * 0.6;

	// Multi-scale normals for aggregate texture
	vec3 norm_base = texture(normal_texture, uv_base).rgb;
	vec3 norm_detail = texture(normal_texture, uv_detail).rgb;
	vec3 norm = normalize(
		vec3(norm_base.xy + (norm_detail.xy - 0.5) * 0.6, norm_base.z)
	);

	// Water fills from bottom up
	float wet = smoothstep(water_fill - EDGE_SOFT, water_fill + EDGE_SOFT, v_height_norm);
	float wetness = 1.0 - wet;
	vec3 color = mix(soil, soil * 0.6 + WATER_COLOR * 0.4, wetness);

	ALBEDO = color;
	NORMAL_MAP = norm;
	NORMAL_MAP_DEPTH = NORMAL_STRENGTH;
	ROUGHNESS = mix(0.9, 0.3, wetness);
	METALLIC = 0.0;
	SPECULAR = mix(0.15, 0.5, wetness);
	EMISSION = color * emission_strength;
}
