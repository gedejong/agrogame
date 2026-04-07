shader_type canvas_item;
// Gaussian-like background blur for glassmorphism UI panels.
// Uses screen texture sampling with multi-tap blur.
// 25-tap (5x5) for visible frosted glass on HiDPI displays.

uniform float blur_radius : hint_range(0.0, 32.0, 0.5) = 16.0;
uniform vec4 tint_color : source_color = vec4(0.118, 0.145, 0.196, 0.80);
uniform sampler2D screen_tex : hint_screen_texture, filter_linear_mipmap;

void fragment() {
	vec2 px = SCREEN_PIXEL_SIZE * blur_radius;
	// 25-tap box blur (5x5 grid)
	vec4 sum = vec4(0.0);
	for (int x = -2; x <= 2; x++) {
		for (int y = -2; y <= 2; y++) {
			sum += texture(screen_tex, SCREEN_UV + vec2(float(x), float(y)) * px);
		}
	}
	sum /= 25.0;
	// Blend with tint color
	COLOR = mix(sum, tint_color, tint_color.a);
	COLOR.a = 1.0;
}
