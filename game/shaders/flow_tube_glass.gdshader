shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_always;
// Glass tube filled with colored liquid. No animation on the tube itself —
// particles handle the flow visualization.

uniform vec4 liquid_color : source_color = vec4(0.376, 0.647, 0.980, 0.8);
uniform float fill_level : hint_range(0.0, 1.0, 0.05) = 0.7;

void fragment() {
	// Rim lighting for glass roundness
	float ndv = abs(dot(NORMAL, VIEW));
	float rim = pow(1.0 - ndv, 3.0);

	// Liquid fill: center of cylinder is liquid, edges are glass
	float circ = abs(NORMAL.x);
	float in_liquid = smoothstep(1.0 - fill_level, 1.0 - fill_level + 0.1, 1.0 - circ);

	vec3 glass = vec3(0.88, 0.92, 0.96);
	ALBEDO = mix(glass, liquid_color.rgb, in_liquid);
	ALPHA = mix(0.1 + rim * 0.15, liquid_color.a, in_liquid);
	EMISSION = liquid_color.rgb * in_liquid * 0.1;
	METALLIC = mix(0.2, 0.0, in_liquid);
	ROUGHNESS = mix(0.05, 0.4, in_liquid);
}
