shader_type spatial;
// Stem shader: color + wind sway. Thin tall stems flex more.
// Base stays fixed, top sways. Matches leaf shader wind uniforms.

uniform vec3 stem_color : source_color = vec3(0.3, 0.5, 0.2);
uniform float wind_strength : hint_range(0.0, 1.0) = 0.0;
uniform vec2 wind_direction = vec2(1.0, 0.0);
// Flexibility: higher = more sway. Thin stems ~1.0, thick ~0.2.
uniform float flexibility : hint_range(0.0, 1.5) = 0.5;

void vertex() {
	if (wind_strength > 0.001 && flexibility > 0.001) {
		// CylinderMesh: VERTEX.y ranges from -height/2 to +height/2.
		// Normalize to 0 (base) .. 1 (top) using model matrix height.
		// MODEL_MATRIX[1][1] is the Y scale = height proxy.
		float stem_height = length(MODEL_MATRIX[1].xyz);
		float norm_y = clamp((VERTEX.y / max(stem_height, 0.01)) + 0.5, 0.0, 1.0);

		// Sway: quadratic from base (0) to top (1), like a flexible rod.
		vec3 world_pos = MODEL_MATRIX[3].xyz;
		float spatial_offset = dot(vec2(world_pos.x, world_pos.z), wind_direction) * 2.0;
		float freq = 2.0 + wind_strength * 2.0;
		float phase = TIME * freq + spatial_offset;
		float sway = sin(phase) * norm_y * norm_y * wind_strength * flexibility * 0.15;
		sway += sin(phase * 1.7 + 0.5) * norm_y * norm_y * wind_strength * flexibility * 0.05;
		VERTEX.x += wind_direction.x * sway;
		VERTEX.z += wind_direction.y * sway;
	}
}

void fragment() {
	ALBEDO = stem_color;
	ROUGHNESS = 0.8;
	METALLIC = 0.0;
}
