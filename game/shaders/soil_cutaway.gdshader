shader_type spatial;
// Soil cutaway layer — triplanar procedural grain + subtle water fill.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform vec4 tint_color : source_color = vec4(1.0);
uniform float water_fill : hint_range(0.0, 1.0) = 0.0;
uniform float box_height : hint_range(0.01, 2.0) = 0.25;
uniform float emission_strength : hint_range(0.0, 1.0) = 0.1;

const vec3 WATER_COLOR = vec3(0.25, 0.4, 0.6);
const float EDGE_SOFT = 0.02;

varying float v_height_norm;
varying vec3 v_world_pos;
varying vec3 v_world_normal;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float value_noise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	float a = hash(i);
	float b = hash(i + vec2(1.0, 0.0));
	float c = hash(i + vec2(0.0, 1.0));
	float d = hash(i + vec2(1.0, 1.0));
	return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
	float v = 0.0;
	float a = 0.5;
	for (int i = 0; i < 4; i++) {
		v += a * value_noise(p);
		p *= 2.1;
		a *= 0.5;
	}
	return v;
}

// Triplanar noise: pick coordinate pair based on face normal
float tri_fbm(vec3 wp, vec3 n, float freq) {
	vec3 blend = abs(n);
	blend /= (blend.x + blend.y + blend.z);
	float xy = fbm(wp.xy * freq);
	float xz = fbm(wp.xz * freq);
	float yz = fbm(wp.yz * freq);
	return xy * blend.z + xz * blend.y + yz * blend.x;
}

void vertex() {
	v_height_norm = (VERTEX.y / box_height) + 0.5;
	v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	v_world_normal = (MODEL_MATRIX * vec4(NORMAL, 0.0)).xyz;
}

void fragment() {
	vec2 uv2 = UV * 2.0;
	vec3 soil = texture(albedo_texture, uv2).rgb * tint_color.rgb;
	vec3 wn = normalize(v_world_normal);

	// Triplanar procedural grain — no stretching on any face
	float grain = tri_fbm(v_world_pos, wn, 80.0);
	float coarse = tri_fbm(v_world_pos + vec3(5.0, 2.0, 0.0), wn, 25.0);
	float cracks = smoothstep(0.47, 0.50, tri_fbm(v_world_pos + vec3(1.3, 4.7, 0.0), wn, 40.0));
	soil *= 0.85 + coarse * 0.3;
	soil *= 0.9 + (grain - 0.5) * 0.2;
	soil *= 1.0 - cracks * 0.25;

	// Triplanar procedural normal
	vec3 tex_norm = texture(normal_texture, uv2).rgb;
	float eps = 0.001;
	float nx = tri_fbm(v_world_pos + vec3(eps, 0, 0), wn, 60.0) - tri_fbm(v_world_pos - vec3(eps, 0, 0), wn, 60.0);
	float ny = tri_fbm(v_world_pos + vec3(0, eps, 0), wn, 60.0) - tri_fbm(v_world_pos - vec3(0, eps, 0), wn, 60.0);
	vec3 proc_norm = normalize(vec3(nx * 8.0, ny * 8.0, 1.0)) * 0.5 + 0.5;
	vec3 norm = normalize(
		vec3(tex_norm.xy + (proc_norm.xy - 0.5) * 0.7, tex_norm.z)
	);

	// Water: subtle darkening + slight tint
	float wet = smoothstep(water_fill - EDGE_SOFT, water_fill + EDGE_SOFT, v_height_norm);
	float wetness = 1.0 - wet;
	vec3 color = mix(soil, soil * 0.7 + WATER_COLOR * 0.15, wetness);

	ALBEDO = color;
	NORMAL_MAP = norm;
	NORMAL_MAP_DEPTH = 2.0;
	ROUGHNESS = mix(0.9, 0.25, wetness) + (1.0 - grain) * 0.08;
	METALLIC = 0.0;
	SPECULAR = mix(0.15, 0.6, wetness);
	EMISSION = color * emission_strength;
}
