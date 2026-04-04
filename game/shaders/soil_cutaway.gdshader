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
const float BEVEL_WIDTH = 0.06;

varying float v_height_norm;
varying vec3 v_local_pos;

void vertex() {
	v_height_norm = (VERTEX.y / box_height) + 0.5;
	v_local_pos = VERTEX;
}

void fragment() {
	vec3 soil = texture(albedo_texture, UV).rgb * tint_color.rgb;
	vec3 norm = texture(normal_texture, UV).rgb;

	// Water fills from bottom up
	float wet = smoothstep(water_fill - EDGE_SOFT, water_fill + EDGE_SOFT, v_height_norm);
	float wetness = 1.0 - wet;
	vec3 color = mix(soil, soil * 0.65 + WATER_COLOR * 0.35, wetness);

	// Fake rounded edges: darken near box edges using UV proximity.
	// UV goes 0→1 across each face. Edges are at UV=0 and UV=1.
	float edge_x = min(UV.x, 1.0 - UV.x);
	float edge_y = min(UV.y, 1.0 - UV.y);
	float edge_dist = min(edge_x, edge_y);
	float edge_darken = smoothstep(0.0, BEVEL_WIDTH, edge_dist);
	color *= mix(0.7, 1.0, edge_darken);

	// Fake edge normal: bend normal outward near edges for highlight/shadow
	vec3 edge_normal = norm;
	float nx_bend = smoothstep(BEVEL_WIDTH, 0.0, edge_x) * sign(UV.x - 0.5);
	float ny_bend = smoothstep(BEVEL_WIDTH, 0.0, edge_y) * sign(UV.y - 0.5);
	edge_normal.x += nx_bend * 0.4;
	edge_normal.y += ny_bend * 0.4;

	ALBEDO = color;
	NORMAL_MAP = normalize(edge_normal);
	ROUGHNESS = mix(0.9, 0.5, wetness);
	METALLIC = 0.0;
	EMISSION = color * emission_strength;
}
