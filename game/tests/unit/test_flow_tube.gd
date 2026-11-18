extends GutTest
## Tests for FlowTube glass-tube component.

const FlowTubeRef = preload("res://scripts/flow_tube.gd")


func test_create_returns_node() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_not_null(tube)
	assert_gt(tube.get_child_count(), 0, "Should have mesh + particles children")


func test_zero_length_tube_no_crash() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3.ZERO,
				"end": Vector3.ZERO,
				"color": Color.RED,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_not_null(tube)


func test_radius_scales_with_magnitude() -> void:
	var thin: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.3, 0),
				"color": Color.GREEN,
				"magnitude": 0.1,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(thin)
	var thick: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0.2, 0, 0),
				"end": Vector3(0.2, -0.3, 0),
				"color": Color.GREEN,
				"magnitude": 1.0,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(thick)
	# Find CylinderMesh children and compare radii
	var thin_r := _get_tube_radius(thin)
	var thick_r := _get_tube_radius(thick)
	assert_gt(thick_r, thin_r, "Higher magnitude should produce larger radius")


func test_label_created_when_text_provided() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
				"label_text": "Test Label",
			}
		)
	)
	add_child_autofree(tube)
	var has_label := false
	for child: Node in tube.get_children():
		if child is Label3D:
			has_label = true
	assert_true(has_label, "Should have a Label3D when label_text provided")


func test_no_label_when_empty() -> void:
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	for child: Node in tube.get_children():
		assert_false(child is Label3D, "No Label3D without label_text")


func test_fade_in_sets_transparent() -> void:
	var tube: FlowTube = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.BLUE,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	tube.fade_in(0.1)
	# Material alpha should start at 0
	assert_lt(tube._material.albedo_color.a, 0.01, "Should start transparent")


func test_pulse_no_crash() -> void:
	var tube: FlowTube = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.GREEN,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	var orig_energy: float = tube._material.emission_energy_multiplier
	tube.pulse(2.0, 0.3)
	assert_gt(
		tube._material.emission_energy_multiplier,
		orig_energy,
		"Emission should be boosted after pulse",
	)


func test_fade_out_schedules_free() -> void:
	var tube: FlowTube = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, -0.2, 0),
				"color": Color.RED,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child(tube)
	tube.fade_out(0.1)
	# Material exists and tween is running (tube not yet freed)
	assert_not_null(tube._material, "Material should exist during fade")


func test_gas_dissipation_sets_gravity() -> void:
	var tube: FlowTube = (
		FlowTubeRef
		. create(
			{
				"start": Vector3(0, 0, 0),
				"end": Vector3(0, 0.2, 0),
				"color": Color.YELLOW,
				"magnitude": 0.5,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	tube.enable_gas_dissipation()
	if tube._particles and tube._particles.process_material:
		var pm: ParticleProcessMaterial = tube._particles.process_material
		assert_gt(pm.gravity.y, 0.0, "Gas particles should drift upward")


func test_flow_curve_null_for_single_point() -> void:
	# A single-point path has no distinct segment — no curve, no PathFollow3D.
	var curve: Curve3D = FlowTubeRef._build_flow_curve([Vector3(0.1, 0, 0.1)])
	assert_null(curve, "Single-point path must not produce a curve")


func test_flow_curve_null_for_coincident_points() -> void:
	# All points coincident (and near-coincident within epsilon) collapse to
	# <2 distinct points, so no degenerate curve reaches PathFollow3D.
	var pts: Array[Vector3] = [
		Vector3(0.2, 0.0, 0.2),
		Vector3(0.2, 0.0, 0.2),
		Vector3(0.2 + 1e-6, 0.0, 0.2),
	]
	var curve: Curve3D = FlowTubeRef._build_flow_curve(pts)
	assert_null(curve, "Coincident/near-coincident points must not produce a curve")


func test_flow_curve_valid_for_collinear_reversal() -> void:
	# A->B->A reversal previously produced a zero interior tangent handle at B,
	# which makes PathFollow3D invert a zero-determinant basis (det==0). Every
	# retained point must now carry a non-zero tangent.
	var a := Vector3(0.0, 0.0, 0.0)
	var b := Vector3(0.0, -0.15, 0.0)
	var curve: Curve3D = FlowTubeRef._build_flow_curve([a, b, a])
	assert_not_null(curve, "Reversal path should still yield a valid curve")
	assert_gt(curve.point_count, 1, "Curve needs >= 2 points to follow")
	for i in range(curve.point_count):
		var tan_in: Vector3 = curve.get_point_in(i)
		var tan_out: Vector3 = curve.get_point_out(i)
		assert_false(tan_out.is_zero_approx(), "Point %d out-tangent must be non-zero" % i)
		assert_false(tan_in.is_zero_approx(), "Point %d in-tangent must be non-zero" % i)
	assert_gt(curve.get_baked_length(), 0.0, "Baked curve length must be positive")


func test_degenerate_path_tube_attaches_no_path_follow() -> void:
	# Full create() path with a degenerate (all-coincident) point list must not
	# attach any PathFollow3D to a Path3D — the source of the det==0 flood.
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"path": [Vector3(0.3, 0.0, 0.3), Vector3(0.3, 0.0, 0.3), Vector3(0.3, 0.0, 0.3)],
				"color": Color.CYAN,
				"magnitude": 0.6,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_not_null(tube)
	assert_eq(_count_path_follows(tube), 0, "Degenerate curve must have no PathFollow3D")


func test_valid_path_tube_attaches_path_follows() -> void:
	# Regression guard: a genuine multi-point path still animates particles.
	var tube: Node3D = (
		FlowTubeRef
		. create(
			{
				"path":
				[Vector3(0.0, 0.0, 0.0), Vector3(0.0, -0.1, 0.05), Vector3(0.02, -0.2, 0.1)],
				"color": Color.CYAN,
				"magnitude": 0.8,
				"speed": 1.0,
			}
		)
	)
	add_child_autofree(tube)
	assert_gt(_count_path_follows(tube), 0, "Valid path should attach PathFollow3D particles")


func test_tween_magnitude_path_tube_creates_no_tween() -> void:
	# #520: a path tube has an ArrayMesh and PathFollow3D particles, so neither
	# tweener applied and Godot logged "started with no Tweeners".
	var tube: FlowTube = FlowTubeRef.create(
		{"path": [Vector3.ZERO, Vector3(0, -0.1, 0.05), Vector3(0.02, -0.2, 0.1)], "magnitude": 0.5}
	)
	add_child_autofree(tube)
	var mesh: Mesh = tube._tube_mesh.mesh
	var before: Array[Tween] = get_tree().get_processed_tweens()
	tube.tween_magnitude(0.6)
	assert_eq(_new_tweens(before).size(), 0, "Path tube must create no tween")
	assert_same(tube._tube_mesh.mesh, mesh, "Path tube mesh must be left alone")
	await wait_process_frames(3)
	assert_engine_error_count(0, "No 'started with no Tweeners' engine error")


func test_tween_magnitude_cylinder_tweens_radius_to_target() -> void:
	# #565: step the tween by hand. CylinderMesh.set_top_radius drops a write
	# within CMP_EPSILON (1e-5) of the current radius, so when a frame left the
	# radius that close to the target, the final write was lost and the radius
	# stayed short. Fixed steps keep the final write half the change wide.
	var tube := _make_cylinder_tube(0.5, Vector3(0, -0.2, 0))
	var start := _get_tube_radius(tube)
	var target := lerpf(FlowTubeRef.MIN_RADIUS, FlowTubeRef.MAX_RADIUS, sqrt(0.8))
	var before: Array[Tween] = get_tree().get_processed_tweens()
	tube.tween_magnitude(0.8, 0.05)
	var created := _new_tweens(before)
	assert_eq(created.size(), 1, "Cylinder tube creates exactly one tween")
	var tw: Tween = created[0]
	tw.pause()  # before any frame, so only custom_step advances it
	watch_signals(tw)
	tw.custom_step(0.025)
	# Margins, not bare bounds: the radius is stored as float32, so a snap to the
	# target reads back just below the float64 target and would pass assert_lt.
	var mid := _get_tube_radius(tube)
	assert_gt(mid, start + 1e-6, "Radius has left the build radius at mid-tween")
	assert_lt(mid, target - 1e-6, "Radius is still short of the target at mid-tween")
	assert_signal_not_emitted(tw, "finished", "Tween is still running at mid-tween")
	tw.custom_step(0.05)
	assert_signal_emitted(tw, "finished", "Tween finishes once its duration has elapsed")
	assert_almost_eq(_get_tube_radius(tube), target, 1e-6, "Radius reaches the AC1 target")


func test_tween_magnitude_degenerate_cylinder_creates_no_tween() -> void:
	# start == end builds neither mesh nor particles, so there is nothing to tween.
	var tube := _make_cylinder_tube(0.5, Vector3.ZERO)
	var before: Array[Tween] = get_tree().get_processed_tweens()
	tube.tween_magnitude(0.6)
	assert_eq(_new_tweens(before).size(), 0, "Degenerate tube must create no tween")


func test_tween_magnitude_particle_count_matches_build() -> void:
	# #520 AC2: an identical refresh kept 30 particles at 0.5 but main cut them to
	# 10 (x20, 2..20 against _build_particles' x60, 1..60).
	var tube := _make_cylinder_tube(0.5, Vector3(0, -0.2, 0))
	assert_eq(tube._particles.amount, 30, "Build count at magnitude 0.5")
	var before: Array[Tween] = get_tree().get_processed_tweens()
	tube.tween_magnitude(0.5, 0.05)
	await wait_for_signal(_new_tweens(before)[0].finished, 1.0)
	assert_eq(tube._particles.amount, 30, "Same magnitude keeps the build count")
	before = get_tree().get_processed_tweens()
	tube.tween_magnitude(0.8, 0.05)
	await wait_for_signal(_new_tweens(before)[0].finished, 1.0)
	assert_eq(tube._particles.amount, 48, "New magnitude gets _build_particles' count")


func _make_cylinder_tube(magnitude: float, end: Vector3) -> FlowTube:
	var tube: FlowTube = FlowTubeRef.create(
		{"start": Vector3.ZERO, "end": end, "color": Color.BLUE, "magnitude": magnitude}
	)
	add_child_autofree(tube)
	return tube


func _new_tweens(before: Array[Tween]) -> Array[Tween]:
	var created: Array[Tween] = []
	for tw: Tween in get_tree().get_processed_tweens():
		if not before.has(tw):
			created.append(tw)
	return created


func _count_path_follows(node: Node) -> int:
	var n := 0
	for child: Node in node.get_children():
		if child is PathFollow3D:
			n += 1
		n += _count_path_follows(child)
	return n


func _get_tube_radius(tube: Node3D) -> float:
	for child: Node in tube.get_children():
		if child is MeshInstance3D:
			var mi: MeshInstance3D = child as MeshInstance3D
			if mi.mesh is CylinderMesh:
				return (mi.mesh as CylinderMesh).top_radius
	return 0.0
