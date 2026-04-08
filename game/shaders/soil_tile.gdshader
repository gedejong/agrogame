shader_type spatial;
render_mode cull_disabled;
// Soil tile — PBR with procedural grain noise, world-space coordinates.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform float som_frac : hint_range(0.0, 1.0) = 0.0;
uniform float moisture_frac : hint_range(0.0, 1.0) = 0.0;
uniform float selected : hint_range(0.0, 1.0) = 0.0;

const vec3 SOM_DARK = vec3(0.4, 0.3, 0.2);
const float SOM_STRENGTH = 0.7;
const vec3 MOISTURE_DARK = vec3(0.55, 0.55, 0.6);
const float MOISTURE_STRENGTH = 0.5;

varying vec3 v_world_pos;

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

void vertex() {
	v_world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	vec2 uv2 = UV * 2.0;
	vec3 color = texture(albedo_texture, uv2).rgb;

	// World-space noise for uniform grain across all tiles
	vec2 wp = v_world_pos.xz;
	float grain_fine = fbm(wp * 80.0);
	float grain_coarse = fbm(wp * 25.0);
	float cracks = smoothstep(0.48, 0.50, fbm(wp * 40.0 + vec2(3.7, 1.2)));

	color *= 0.85 + grain_coarse * 0.3;
	color *= 0.9 + (grain_fine - 0.5) * 0.25;
	color *= 1.0 - cracks * 0.3;

	// SOM / moisture
	color = mix(color, color * SOM_DARK, som_frac * SOM_STRENGTH);
	color = mix(color, color * MOISTURE_DARK, moisture_frac * MOISTURE_STRENGTH);

	// Normal from world-space noise gradient + texture
	vec3 tex_norm = texture(normal_texture, uv2).rgb;
	float eps = 0.001;
	float nx = fbm(wp * 60.0 + vec2(eps, 0.0)) - fbm(wp * 60.0 - vec2(eps, 0.0));
	float ny = fbm(wp * 60.0 + vec2(0.0, eps)) - fbm(wp * 60.0 - vec2(0.0, eps));
	vec3 proc_norm = normalize(vec3(nx * 8.0, ny * 8.0, 1.0)) * 0.5 + 0.5;
	vec3 norm = normalize(
		vec3(tex_norm.xy + (proc_norm.xy - 0.5) * 0.7, tex_norm.z)
	);

	// Selection: thin gold border along tile edges
	float border_w = 0.04;
	float edge = min(min(UV.x, 1.0 - UV.x), min(UV.y, 1.0 - UV.y));
	float border = 1.0 - smoothstep(border_w - 0.01, border_w, edge);
	vec3 sel_color = vec3(1.0, 0.85, 0.3);

	ALBEDO = color;
	NORMAL_MAP = norm;
	NORMAL_MAP_DEPTH = 1.8;
	ROUGHNESS = mix(0.85, 0.3, moisture_frac) + (1.0 - grain_fine) * 0.1;
	METALLIC = 0.0;
	SPECULAR = mix(0.2, 0.5, moisture_frac);
	EMISSION = sel_color * border * selected * 0.6;
}
