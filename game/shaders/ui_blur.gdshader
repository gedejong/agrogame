shader_type canvas_item;
// Glassmorphism background blur for UI panels.
// Two-pass approach: sample screen at offset taps, average, tint.

uniform float blur_amount : hint_range(0.0, 10.0, 0.1) = 3.0;
uniform vec4 tint_color : source_color = vec4(0.118, 0.145, 0.196, 0.80);
uniform sampler2D screen_tex : hint_screen_texture, filter_linear;

void fragment() {
	vec2 ps = SCREEN_PIXEL_SIZE * blur_amount;

	// 13-tap cross + diagonal kernel for visible blur
	vec4 col = texture(screen_tex, SCREEN_UV);
	col += texture(screen_tex, SCREEN_UV + vec2(ps.x, 0.0));
	col += texture(screen_tex, SCREEN_UV + vec2(-ps.x, 0.0));
	col += texture(screen_tex, SCREEN_UV + vec2(0.0, ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(0.0, -ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(ps.x, ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(-ps.x, ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(ps.x, -ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(-ps.x, -ps.y));
	col += texture(screen_tex, SCREEN_UV + vec2(ps.x * 2.0, 0.0));
	col += texture(screen_tex, SCREEN_UV + vec2(-ps.x * 2.0, 0.0));
	col += texture(screen_tex, SCREEN_UV + vec2(0.0, ps.y * 2.0));
	col += texture(screen_tex, SCREEN_UV + vec2(0.0, -ps.y * 2.0));
	col /= 13.0;

	// Tint blend
	COLOR.rgb = mix(col.rgb, tint_color.rgb, tint_color.a);
	COLOR.a = 1.0;
}
