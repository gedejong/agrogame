shader_type spatial;
// Soil cutaway layer shader — blends soil texture with water.
// Water permeates from the bottom up based on fill level.

uniform sampler2D albedo_texture : source_color;
uniform sampler2D normal_texture : hint_normal;
uniform vec4 tint_color : source_color = vec4(1.0);
uniform float water_fill : hint_range(0.0, 1.0) = 0.0;
uniform float emission_strength : hint_range(0.0, 1.0) = 0.15;

const vec3 WATER_COLOR = vec3(0.3, 0.55, 0.85);
// Soft gradient width at the water line (in normalized Y space)
const float WATER_EDGE_SOFTNESS = 0.08;

void fragment() {
	vec3 soil = texture(albedo_texture, UV).rgb * tint_color.rgb;

	// Local Y of the vertex in the box: MODEL_MATRIX maps local → world.
	// Box is centered at origin, so local Y ranges from -0.5 to +0.5.
	// We want water_fill=1.0 → fully wet, water_fill=0 → fully dry.
	// Water fills from bottom (-0.5) upward. Normalize Y to [0,1]:
	float y_norm = UV.y;  // For triplanar this won't work perfectly,
	// so use the world-space approach via VERTEX:
	// Box height is encoded in the mesh. VERTEX.y ranges -h/2 to +h/2.
	// Normalize: 0 = bottom, 1 = top.
	float box_y = clamp(VERTEX.y / max(abs(VERTEX.y) + 0.001, 0.001), -1.0, 1.0);
	// Actually, since box is centered, bottom = -0.5*h, top = +0.5*h.
	// Use a simpler approach: the bottom of the box has low UV.y.
	// With triplanar, UV varies per face. Use VERTEX.y directly:
	// Remap VERTEX.y: value < 0 = lower half, > 0 = upper half.
	// water_fill of 0.5 means bottom half is wet.
	// Wet threshold in normalized coords: (1.0 - water_fill) maps to VERTEX.y.
	// Since box center is at 0, top is at +h/2, bottom at -h/2:
	// wet_line_y = lerp(bottom, top, water_fill) = lerp(-0.5, 0.5, water_fill)
	// But we don't know h here. Use object-space: normalize to [-1, 1].

	// Simpler: use a varying set in vertex().
	// For now, approximate with UV.y which works on side faces.
	float wet_line = 1.0 - water_fill;
	float wet_amount = smoothstep(wet_line - WATER_EDGE_SOFTNESS, wet_line + WATER_EDGE_SOFTNESS, UV.y);

	vec3 wet_soil = mix(soil, soil * 0.7 + WATER_COLOR * 0.3, wet_amount);

	ALBEDO = wet_soil;
	NORMAL_MAP = texture(normal_texture, UV).rgb;
	ROUGHNESS = mix(0.9, 0.6, wet_amount);  // Wet soil is shinier
	METALLIC = 0.0;
	EMISSION = wet_soil * emission_strength;
}
