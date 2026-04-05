shader_type spatial;
render_mode cull_disabled;
// Shared crop leaf shader — alpha mask + green/yellow senescence.

uniform sampler2D alpha_mask : source_color;
uniform vec3 base_color : source_color = vec3(0.2, 0.55, 0.15);
uniform float senescence : hint_range(0.0, 1.0) = 0.0;
uniform float stress : hint_range(0.0, 1.0) = 0.0;

const vec3 GREEN = vec3(0.2, 0.55, 0.15);
const vec3 YOUNG_GREEN = vec3(0.35, 0.65, 0.25);
const vec3 SENESCENT = vec3(0.7, 0.6, 0.2);
const vec3 DEAD = vec3(0.5, 0.4, 0.2);
const vec3 WILTING = vec3(0.45, 0.38, 0.18);

void fragment() {
	float mask = texture(alpha_mask, UV).r;
	if (mask < 0.3) {
		discard;
	}

	// Color based on senescence
	vec3 color = mix(YOUNG_GREEN, base_color, smoothstep(0.0, 0.3, senescence + 0.5));
	color = mix(color, SENESCENT, smoothstep(0.0, 0.7, senescence));
	color = mix(color, DEAD, smoothstep(0.5, 1.0, senescence));

	// Stress overlay
	color = mix(color, WILTING, stress * 0.5);

	ALBEDO = color;
	ROUGHNESS = 0.7;
	METALLIC = 0.0;
	ALPHA_SCISSOR_THRESHOLD = 0.3;
	ALPHA = mask;
}
