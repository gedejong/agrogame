shader_type spatial;
// Culm, sheath column, peduncle and petiole shader: flat colour, bending
// with the whole plant. A cylinder's origin is its centre, so the base
// vertex sits origin_height below the origin and stays on the ground.
#include "res://shaders/crop_wind.gdshaderinc"

uniform vec3 stem_color : source_color = vec3(0.3, 0.5, 0.2);

void vertex() {
	if (wind_strength > 0.001 && plant_flex > 0.001) {
		vec3 v = VERTEX;
		WindFrame f = wind_frame(MODEL_MATRIX, TIME, INSTANCE_CUSTOM.r);
		VERTEX += wind_plant_bend(f, v);
	}
}

void fragment() {
	ALBEDO = stem_color;
	ROUGHNESS = 0.8;
	METALLIC = 0.0;
}
