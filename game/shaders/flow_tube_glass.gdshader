shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_always;
// Glass tube with animated liquid fill for flow visualization.

uniform vec4 liquid_color : source_color = vec4(0.376, 0.647, 0.980, 0.8);
uniform float flow_speed : hint_range(-5.0, 5.0, 0.1) = 1.0;
uniform float fill_level : hint_range(0.0, 1.0, 0.05) = 0.7;

void fragment() {
	// UV.y runs along tube; scroll for flow animation
	float scroll = UV.y + TIME * flow_speed;
	float droplets = smoothstep(0.35, 0.65, sin(scroll * 15.0) * 0.5 + 0.5);

	// Rim lighting for glass roundness (NORMAL-based, works on cylinder)
	float ndv = abs(dot(NORMAL, VIEW));
	float rim = pow(1.0 - ndv, 3.0);

	// Liquid fill: use NORMAL.x to detect front/back of cylinder cross-section
	float circ = abs(NORMAL.x);
	float in_liquid = smoothstep(1.0 - fill_level, 1.0 - fill_level + 0.1, 1.0 - circ);

	vec3 glass = vec3(0.85, 0.9, 0.95);
	vec3 liquid = liquid_color.rgb * (1.0 + droplets * 0.2);
	ALBEDO = mix(glass, liquid, in_liquid);
	ALPHA = mix(0.12 + rim * 0.2, liquid_color.a, in_liquid);
	EMISSION = liquid_color.rgb * in_liquid * 0.15;
	METALLIC = 0.1;
	ROUGHNESS = mix(0.1, 0.5, in_liquid);
}
