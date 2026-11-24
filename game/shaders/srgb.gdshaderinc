// sRGB to linear conversion for colours authored in sRGB.
//
// Every hand-typed colour in this project is sRGB: Godot's Color, the
// inspector's colour picker and the texture files all use it. The renderer
// shades in linear light, so an sRGB literal used as if it were linear
// renders two to four times too bright and washed out (#637). Convert it
// once, where it enters the shader.
//
// A source_color uniform is converted by the engine only when it is set
// from a Color; a Vector3 goes in unchanged. Colour literals in shader code
// and vertex colours are never converted, so they go through this macro.
//
// Transfer function: IEC 61966-2-1:1999 (sRGB), the curve the engine applies
// to source_color uniforms (Color.srgb_to_linear). It is a macro, not a
// function, so a const may be initialised with it and is folded at compile
// time.
#define SRGB_TO_LINEAR(c) mix(pow(((c) + vec3(0.055)) / 1.055, vec3(2.4)), (c) / 12.92, lessThan((c), vec3(0.04045)))
