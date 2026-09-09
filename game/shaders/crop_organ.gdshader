shader_type spatial;
render_mode cull_disabled;
// Reproductive organs and fruit (spikes, panicles, ears, tassels, bunches):
// a plain double-sided surface tinted by the mesh's vertex colours, carried
// by the whole-plant wind bend and swinging on its own stalk. The mesh
// origin is the organ's attachment point.
#include "res://shaders/crop_wind.gdshaderinc"

uniform vec3 albedo : source_color = vec3(1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.75;
// Free-end swing of this organ: 1 for a head nodding on its peduncle, 0 for
// an organ held fast against the culm.
uniform float sway : hint_range(0.0, 1.0) = 1.0;

void vertex() {
	if (wind_strength > 0.001) {
		vec3 v = VERTEX;
		WindFrame f = wind_frame(MODEL_MATRIX, TIME, INSTANCE_CUSTOM.r);
		VERTEX += wind_plant_bend(f, v) + wind_head_sway(f, length(v) * sway);
	}
}

void fragment() {
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	ALBEDO = albedo * COLOR.rgb;
	ROUGHNESS = roughness;
	METALLIC = 0.0;
}
