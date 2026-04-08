shader_type spatial;
render_mode blend_mix, cull_disabled, depth_draw_opaque;
// Glass tube with animated liquid fill for flow visualization.
// Outer shell is transparent glass; inner fill scrolls to show flow.

uniform vec4 liquid_color : source_color = vec4(0.376, 0.647, 0.980, 0.8);
uniform float flow_speed : hint_range(-5.0, 5.0, 0.1) = 1.0;
uniform float fill_level : hint_range(0.0, 1.0, 0.05) = 0.7;
uniform float glass_opacity : hint_range(0.0, 1.0, 0.05) = 0.2;

void fragment() {
	// UV.y runs along tube length; UV.x wraps around circumference
	float scroll = UV.y + TIME * flow_speed;
	// Animated bubble/droplet pattern
	float wave = sin(scroll * 12.0) * 0.5 + 0.5;
	float bubbles = smoothstep(0.3, 0.7, wave);

	// Glass shell: rim-lit transparent tube
	float rim = pow(1.0 - abs(dot(NORMAL, VIEW)), 2.0);
	vec3 glass_col = vec3(0.9, 0.95, 1.0);

	// Liquid fill: only inside the fill_level fraction of the cross-section
	// Use UV.x (circumference) to determine if this fragment is "liquid"
	float dist_from_center = abs(UV.x - 0.5) * 2.0;
	float in_liquid = step(dist_from_center, fill_level);

	vec3 col = mix(glass_col, liquid_color.rgb, in_liquid);
	// Add bubble highlights in the liquid
	col += vec3(bubbles * 0.15) * in_liquid;

	ALBEDO = col;
	ALPHA = mix(glass_opacity + rim * 0.3, liquid_color.a, in_liquid);
	EMISSION = liquid_color.rgb * in_liquid * 0.1;
}
