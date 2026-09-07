// Shared wind model of the crop shaders (leaf, stem, organ). Every part of a
// plant is bent by the same whole-plant motion, so blades, culm and heads
// stay attached to each other; free ends flutter on top of it.
//
//   1. Plant bend: the plant holds a lean downwind and rocks about it at its
//      natural sway rate (tall plants slowly, short ones quickly), the
//      displacement growing with height squared like a flexible rod.
//      Neighbours rock in a travelling wave a few plant heights long, the
//      way a cereal stand waves under a breeze (honami; Finnigan 1979).
//   2. Part sway: a blade tip or a head on its peduncle swings on its own
//      rhythm, out of step with its neighbours. Blades flutter slowly and
//      mostly at the tip; heads nod quicker, like short pendulums.
//
// Gusts travel downwind as uneven patches a few metres across: neighbouring
// plants move together, distant ones do not, and the field never moves in
// step. The fronts of the stand's wave meander, and every plant sits a
// little off the stand's rhythm by its own random number, so the wave runs
// ragged across the field rather than as ruled bars. Amplitudes follow the
// wind load, which grows faster than the wind speed in a breeze and levels
// off in a gale (see wind_load): a light breeze barely stirs the crop, a
// gale bends it firmly but never flattens it.
//
// All lengths and rates are in the plant's own model units (metres) and
// seconds, independent of the scale the plant is drawn at. Per-mesh data
// arrives as uniforms of the mesh's own material, stamped by the renderer
// post-pass (crop_renderer_3d.gd stamp_wind_frame): plant_height is the
// height of the whole plant, origin_height the height of this mesh's origin
// above the plant base, plant_flex the species' stem flexibility (0 rigid,
// 1 a thin cereal culm), plant_jitter the plant's own random number in
// [0, 1). A MultiMesh layer draws one sample mesh with its material for all
// the plants of a stand, so there each plant's random number rides in the
// instance custom data instead (INSTANCE_CUSTOM.r, passed into wind_frame);
// the two are summed and one of them is always 0. These are material
// uniforms, not instance uniforms: the engine keeps per-instance uniforms in
// one buffer sized for a few thousand geometry instances, and a farm of
// stands is drawn by more mesh layers than that.

uniform float wind_strength : hint_range(0.0, 1.0) = 0.0;
// Horizontal wind direction (x, z), normalised.
uniform vec2 wind_direction = vec2(1.0, 0.0);
// Rhythm offset of this part, hashed per mesh so neighbours flutter out of step.
uniform float wind_phase : hint_range(0.0, 6.28) = 0.0;
uniform float plant_height : hint_range(0.01, 10.0) = 1.0;
uniform float origin_height : hint_range(0.0, 10.0) = 0.0;
uniform float plant_flex : hint_range(0.0, 1.0) = 0.5;
uniform float plant_jitter : hint_range(0.0, 1.0) = 0.0;

// Lean of a fully flexible plant top under a wind load of 1 (fraction of height).
const float PLANT_LEAN_MAX = 0.20;
// Wind load the bend levels off towards; a gale (wind_strength 1) gets a
// little under it.
const float LOAD_CAP = 0.55;
// Length of the stand's travelling wave in plant heights.
const float WAVE_LENGTH_HEIGHTS = 4.0;
// Furthest a plant sits off the stand's rhythm, either way (rad).
const float JITTER_RAD = 0.7;
// Tip travel of a blade under a wind load of 1 (fraction of its length).
const float LEAF_SWAY_MAX = 0.10;
// Tip travel of a head on its peduncle under a wind load of 1 (fraction of
// its length): a head swings as a rigid pendulum, so it travels further for
// its length than a blade does.
const float HEAD_SWAY_MAX = 0.35;

struct WindFrame {
	vec3 up; // world up in model space
	vec3 along; // downwind horizontal in model space
	vec3 across; // cross-wind horizontal in model space
	float gust; // local gust factor, 0.3 (lull) .. 1 (gust)
	float jitter; // the plant's own random number, 0 .. 1
	float lean; // current lean of the plant top (fraction of height)
	float phase; // whole-plant rocking phase (rad)
	float wave; // spatial part of the phase: the plant's place in the stand's travelling wave (rad)
	float t; // time (s)
};

float wind_load() {
	// Drag rises with the square of the wind speed, but blades and culms
	// streamline as they bend, which brings the net exponent down to about
	// 1.5 (Vogel 1989). Once streamlined as far as they go, more wind adds
	// little, so the load levels off towards LOAD_CAP.
	float drag = wind_strength * sqrt(wind_strength);
	return LOAD_CAP * tanh(drag / LOAD_CAP);
}

float wind_gust(vec2 ground_m, float t) {
	// Gust fronts run downwind at about the wind speed. Four trains of
	// different spacing (twenty down to five metres) and heading (two along
	// the wind, two well off it) interfere into patches a few metres across
	// that grow, drift and fade, so no bar of motion ever repeats.
	float speed = 2.0 + 4.0 * wind_strength;
	float down = dot(ground_m, wind_direction);
	float side = dot(ground_m, vec2(-wind_direction.y, wind_direction.x));
	float g = 0.45 * sin(0.35 * (down - speed * t))
		+ 0.3 * sin(0.7 * (down - 1.3 * speed * t) + 0.5 * sin(0.35 * side + 0.2 * t))
		+ 0.35 * sin(0.75 * down + 0.5 * side - 0.85 * speed * t + 1.0)
		+ 0.3 * sin(0.85 * down - 1.05 * side - 1.15 * speed * t + 2.6);
	return mix(0.3, 1.0, smoothstep(-0.6, 0.8, g));
}

WindFrame wind_frame(mat4 model, float t, float instance_random) {
	// The model matrix is a rotation with uniform scale, so its transpose
	// carries world directions back into model space (up to scale).
	WindFrame f;
	mat3 rot = mat3(model);
	mat3 inv = transpose(rot);
	f.up = normalize(inv * vec3(0.0, 1.0, 0.0));
	f.along = normalize(inv * vec3(wind_direction.x, 0.0, wind_direction.y));
	f.across = normalize(inv * vec3(-wind_direction.y, 0.0, wind_direction.x));
	f.t = t;
	f.jitter = fract(plant_jitter + instance_random);
	// Where the plant meets the ground, in metres: this mesh's origin, dropped
	// by its height on the plant. Every mesh of one plant then shares gust
	// and phase.
	float world_scale = length(model[1].xyz);
	vec3 ground = (model[3].xyz - rot * (f.up * origin_height)) / world_scale;
	f.gust = wind_gust(ground.xz, t);
	// Natural sway rate of a plant of this height, about 1 Hz for a wheat
	// culm (Sterling et al. 2003) and slower for taller plants. The wave term
	// makes neighbours rock in a travelling wave a few plant heights long
	// (Raupach et al. 1996). Its fronts meander: a plant's place in the wave
	// is shifted by a smooth field that changes across the wind over a few
	// plant heights and drifts slowly, and by the plant's own random number,
	// so the fronts run ragged rather than ruled.
	float h = max(plant_height, 0.15);
	float omega = 5.0 / sqrt(h);
	float down = dot(ground.xz, wind_direction);
	float side = dot(ground.xz, vec2(-wind_direction.y, wind_direction.x));
	float meander = 0.9 * sin(1.25 * side / h + 0.4 * down / h + 0.13 * t)
		+ 0.6 * sin(2.7 * side / h - 0.9 * down / h + 0.21 * t + 1.7);
	f.wave = -TAU / (WAVE_LENGTH_HEIGHTS * h) * down + meander + (f.jitter - 0.5) * 2.0 * JITTER_RAD;
	f.phase = omega * t + f.wave;
	// The rock modulates the held lean with a weaker off-beat overtone. A thin
	// culm swings from upright to its full lean as the wave passes; a stout
	// stalk only breathes about its lean. Plants also differ a little in how
	// much wind they catch.
	float depth = 0.25 + 0.3 * plant_flex;
	float swing = (sin(f.phase) + 0.25 * sin(f.phase * 1.61 + 1.2)) / 1.25;
	float exposure = 0.85 + 0.3 * f.jitter;
	f.lean = wind_load() * PLANT_LEAN_MAX * plant_flex * f.gust * exposure * (1.0 - depth + depth * swing);
	return f;
}

vec3 wind_plant_bend(WindFrame f, vec3 v) {
	// Rod bend: downwind displacement grows with the square of the height
	// above the base, which stays put; a bent rod also stands a little lower
	// and wanders slightly across the wind.
	float h = max(plant_height, 0.05);
	float y = max(origin_height + dot(v, f.up), 0.0);
	float yn = y / h;
	float d = f.lean * yn * yn * h;
	float drop = 0.667 * f.lean * f.lean * yn * yn * yn * h;
	float wobble = 0.15 * d * sin(f.phase * 0.83 + 2.0 + f.jitter * TAU);
	return f.along * d + f.across * wobble - f.up * drop;
}

vec3 wind_part_sway(WindFrame f, float lever, float reach, float rate, float travel, float lift) {
	// Own swing of a free end about its attachment: lever is the distance
	// from the attachment, reach how far the swing has built up along the
	// part (0 at the attachment, 1 at the tip), rate the swing rate (rad/s)
	// carrying a weaker off-beat overtone, travel the tip travel under a wind
	// load of 1 as a fraction of lever, lift the share of the swing that goes
	// into vertical flapping. The rhythm is the part's own: its rate sits a
	// little off its neighbours' by the plant's random number, its phase is
	// hashed per mesh and per plant, and it only loosely follows the stand's
	// wave.
	float own_rate = rate * (0.9 + 0.2 * f.jitter);
	float p = own_rate * f.t + wind_phase * 3.0 + f.jitter * TAU + f.wave * 0.3;
	float s = sin(p) + 0.3 * sin(1.7 * p + 1.0);
	float c = sin(0.61 * p + wind_phase);
	float u = sin(p + 1.1) + 0.3 * sin(1.7 * p + 2.4);
	float amp = wind_load() * travel * f.gust * lever * reach;
	return (f.along * (0.8 * s) + f.across * (0.35 * c) + f.up * (lift * u)) * amp;
}

vec3 wind_leaf_sway(WindFrame f, float lever, float reach) {
	// Blade flutter: the stiff collar half hardly moves (reach squared), the
	// tip flaps up and down about as much as it swings along.
	return wind_part_sway(f, lever, reach * reach, 3.0 + 3.0 * wind_strength, LEAF_SWAY_MAX, 0.6);
}

vec3 wind_head_sway(WindFrame f, float lever) {
	// A head nodding on its peduncle: a short pendulum, quicker than the
	// plant it rides on.
	return wind_part_sway(f, lever, 1.0, 4.5 + 3.5 * wind_strength, HEAD_SWAY_MAX, 0.3);
}
