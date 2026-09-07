extends RefCounted
## Procedural 3D grapevine renderer: vertical shoot positioning on a
## bilateral cordon.
## The permanent frame (post, catch wires, trunk and cordon) is always drawn,
## dormant vines included. Green shoots rise from spurs on the cordon between
## the catch wires and arch over once they outgrow the top wire; they carry
## alternate palmate leaves on short petioles. Clusters hang in the fruiting
## zone just above the cordon from bloom (repro > 0) and colour berry by
## berry through veraison. Vine leaves stay green while the fruit ripens;
## they only yellow when the canopy itself is lost.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const Organs = preload("res://scripts/crop_organ_meshes.gd")

const TRUNK_HEIGHT := 0.75
const TRUNK_RADIUS := 0.035
const CORDON_HALF_LENGTH := 0.45
const CORDON_RADIUS := 0.02
const POST_HEIGHT := 1.7
const POST_RADIUS := 0.03
## Catch wires above the cordon; shoots are held upright between them.
const WIRE_HEIGHTS: Array[float] = [1.05, 1.45]
const WIRE_RADIUS := 0.003
## Meshes of the permanent frame: post, two wires, two trunk sections, cordon.
const FRAME_MESHES := 6
const NUM_SHOOTS := 6
const SHOOT_LENGTH := 1.2
## Shoot length held upright by the wires before the tip arches over.
const SHOOT_UPRIGHT := 0.72
const LEAVES_PER_SHOOT := 7
const LEAF_SIZE := 0.16
const PETIOLE_LENGTH := 0.06
const CLUSTER_RADIUS := 0.045
const CLUSTER_LENGTH := 0.14
## Height on the shoot (m above the cordon) of the cluster peduncle.
const CLUSTER_NODE := 0.2

const WOOD := Color(0.36, 0.26, 0.18)
const POST_GREY := Color(0.45, 0.40, 0.34)
const WIRE_GREY := Color(0.62, 0.62, 0.64)
const BERRY_GREEN := Color(0.48, 0.64, 0.32)
const BERRY_RIPE := Color(0.28, 0.10, 0.32)
const BERRY_DRY := Color(0.20, 0.08, 0.22)


static func create_plant(
	growth_progress: float,
	senescence: float,
	stresses: Dictionary,
	repro: float,
	seed_val: int,
	yield_frac: float = 1.0
) -> Node3D:
	var plant := Node3D.new()
	_add_frame(plant, seed_val)
	if growth_progress < 0.05:
		return plant
	var g: float = clampf(growth_progress, 0.0, 1.0)
	# Shoots extend as their leaves unfold: short and leafy early, then long.
	var shoot_len: float = SHOOT_LENGTH * pow(g, 1.3)
	var leaf_scale: float = clampf(g * 1.5, 0.25, 1.0)
	var emergence: float = CR.organ_emergence(repro)
	var fill: float = CR.fill_scale(repro, yield_frac)
	var ripe_t: float = smoothstep(0.3, 0.9, repro)
	var spur_pitch: float = CORDON_HALF_LENGTH * 2.0 / float(NUM_SHOOTS)
	for si in range(NUM_SHOOTS):
		# Hash index block of this shoot: spur offset, vigour, lean z, lean x,
		# node density, cluster size, cluster offset, bend side, bend, bend
		# lean; leaves follow from +10, cluster node at +70.
		var sb: int = 100 + si * 80
		var t_along: float = (float(si) + 0.5) / float(NUM_SHOOTS)
		# Spurs are not spaced evenly along the cordon, and shoots of one vine
		# differ in vigour (+/-15% length).
		var sx: float = lerpf(-CORDON_HALF_LENGTH, CORDON_HALF_LENGTH, t_along)
		sx += (CR.hash_val(seed_val, sb) - 0.5) * spur_pitch * 0.5
		var this_len: float = shoot_len * (0.85 + CR.hash_val(seed_val, sb + 1) * 0.3)
		var shoot := Node3D.new()
		shoot.position = Vector3(sx, TRUNK_HEIGHT, 0)
		shoot.rotation.z = (CR.hash_val(seed_val, sb + 2) - 0.5) * 0.3
		shoot.rotation.x = (CR.hash_val(seed_val, sb + 3) - 0.5) * 0.3
		plant.add_child(shoot)
		var lower_len: float = minf(this_len, SHOOT_UPRIGHT)
		# Each shoot segment owns its material: CR.stamp_wind_frame writes one
		# origin height per material.
		CR.attach_mesh(
			shoot,
			CR.create_stem_mesh(lower_len, 0.006, 0.0045),
			CR.create_stem_material(senescence),
			Vector3(0, lower_len * 0.5, 0)
		)
		_add_leaves(
			shoot, 0.0, lower_len, this_len, g, leaf_scale, senescence, stresses, seed_val, si
		)
		if this_len > SHOOT_UPRIGHT + 0.02:
			# Past the top wire the unsupported tip arches over, across the row.
			var upper := Node3D.new()
			upper.position = Vector3(0, lower_len, 0)
			var bend_side: float = 1.0 if CR.hash_val(seed_val, sb + 7) < 0.5 else -1.0
			upper.rotation.x = bend_side * (0.6 + CR.hash_val(seed_val, sb + 8) * 0.5)
			upper.rotation.z = (CR.hash_val(seed_val, sb + 9) - 0.5) * 0.4
			shoot.add_child(upper)
			var upper_len: float = this_len - lower_len
			CR.attach_mesh(
				upper,
				CR.create_stem_mesh(upper_len, 0.0045, 0.003),
				CR.create_stem_material(senescence),
				Vector3(0, upper_len * 0.5, 0)
			)
			_add_leaves(
				upper,
				lower_len,
				upper_len,
				this_len,
				g,
				leaf_scale,
				senescence,
				stresses,
				seed_val,
				si
			)
		# Clusters on four of the six shoots, hanging just above the cordon.
		if emergence > 0.0 and si % 3 != 1:
			_add_cluster(shoot, emergence, fill, ripe_t, senescence, seed_val, si)
	return plant


static func _add_frame(plant: Node3D, seed_val: int) -> void:
	## Trellis post with catch wires, a slightly crooked trunk in two sections
	## and the horizontal cordon: the permanent structure.
	var wood := CR.create_fixture_material(WOOD, 0.9)
	var post_x: float = CORDON_HALF_LENGTH + 0.08
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(POST_HEIGHT, POST_RADIUS, POST_RADIUS),
		CR.create_fixture_material(POST_GREY, 0.9),
		Vector3(post_x, POST_HEIGHT * 0.5, 0)
	)
	var wire_mat := CR.create_fixture_material(WIRE_GREY, 0.4)
	for wy in WIRE_HEIGHTS:
		CR.attach_mesh(
			plant,
			CR.create_stem_mesh(post_x * 2.0, WIRE_RADIUS, WIRE_RADIUS),
			wire_mat,
			Vector3(0, wy, 0),
			Vector3(0, 0, PI * 0.5)
		)
	# Old trunks are rarely straight: the lower section leans one way and the
	# upper section corrects back to meet the cordon.
	var crook: float = (CR.hash_val(seed_val, 95) - 0.5) * 0.24
	var lower_h: float = TRUNK_HEIGHT * 0.6
	var joint := Vector3(-sin(crook) * lower_h, cos(crook) * lower_h, 0)
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(lower_h, TRUNK_RADIUS, TRUNK_RADIUS * 0.85),
		wood,
		joint * 0.5,
		Vector3(0, 0, crook)
	)
	var top := Vector3(0, TRUNK_HEIGHT, 0)
	var upper_dir: Vector3 = top - joint
	var upper_tilt: float = -atan2(upper_dir.x, upper_dir.y)
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(upper_dir.length(), TRUNK_RADIUS * 0.85, TRUNK_RADIUS * 0.7),
		wood,
		(joint + top) * 0.5,
		Vector3(0, 0, upper_tilt)
	)
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(CORDON_HALF_LENGTH * 2.0, CORDON_RADIUS, CORDON_RADIUS),
		wood,
		top,
		Vector3(0, 0, PI * 0.5)
	)


static func _add_leaves(
	segment: Node3D,
	seg_start: float,
	seg_len: float,
	shoot_len: float,
	growth: float,
	leaf_scale: float,
	senescence: float,
	stresses: Dictionary,
	seed_val: int,
	si: int
) -> void:
	## Palmate leaves alternate along the shoot; the newest, uppermost leaf is
	## still small and pale. Each leaf hangs from a short petiole leaving the
	## shoot on alternate sides of the canopy wall (+-z, across the row), its
	## blade tilted outward from the wall. Only the leaves whose position along
	## the shoot falls inside [seg_start, seg_start + seg_len) are attached to
	## this segment, so a shoot split at the top wire places every leaf once.
	var sb: int = 100 + si * 80
	# Node density differs between shoots (+/-20% leaves per shoot).
	var per_shoot: float = float(LEAVES_PER_SHOOT) * (0.8 + CR.hash_val(seed_val, sb + 4) * 0.4)
	var leaf_count_f: float = growth * per_shoot
	var n_leaves: int = ceili(leaf_count_f)
	for li in range(n_leaves):
		# Hash index block of this leaf: node, size, yaw, pitch, lean.
		var lb: int = sb + 10 + li * 5
		var node_jitter: float = (CR.hash_val(seed_val, lb) - 0.5) * 0.4
		# Leaves spread along the shoot as it stands today, newest at the tip.
		var t: float = minf((float(li) + 0.6 + node_jitter) / maxf(leaf_count_f, 1.0), 0.97)
		var along: float = shoot_len * t
		if along < seg_start or along >= seg_start + seg_len:
			continue
		var age: float = clampf(leaf_count_f - float(li), 0.0, 1.0)
		var size: float = LEAF_SIZE * leaf_scale * lerpf(0.5, 1.0, age)
		size *= 0.8 + CR.hash_val(seed_val, lb + 1) * 0.4
		var side: float = 1.0 if li % 2 == 0 else -1.0
		var yaw: float = (0.0 if side > 0.0 else PI) + (CR.hash_val(seed_val, lb + 2) - 0.5)
		var pitch: float = 0.15 + CR.hash_val(seed_val, lb + 3) * 0.95
		var lean: float = (CR.hash_val(seed_val, lb + 4) - 0.5) * 0.6
		var petiole_len: float = PETIOLE_LENGTH * lerpf(0.5, 1.0, age)
		var node := Node3D.new()
		node.position = Vector3(0, along - seg_start, 0)
		node.rotation = Vector3((CR.hash_val(seed_val, lb + 3) - 0.5) * 0.5, yaw, 0)
		segment.add_child(node)
		CR.attach_mesh(
			node,
			CR.create_stem_mesh(petiole_len, 0.0025, 0.002),
			CR.create_stem_material(senescence),
			Vector3(0, 0, petiole_len * 0.5),
			Vector3(PI * 0.5, 0, 0)
		)
		var hinge := Node3D.new()
		hinge.position = Vector3(0, 0, petiole_len)
		hinge.rotation = Vector3(-pitch, 0, lean)
		node.add_child(hinge)
		var leaf := CR.create_leaf_quad(size, size, Vector3(0, -size * 0.45, 0), Vector3.ZERO)
		leaf.material_override = CR.create_leaf_material("grape", senescence, stresses, t, age)
		hinge.add_child(leaf)


static func _add_cluster(
	shoot: Node3D,
	emergence: float,
	fill: float,
	ripe_t: float,
	senescence: float,
	seed_val: int,
	si: int
) -> void:
	## A bunch on a short peduncle from a low node of the shoot: tiny and green
	## at bloom, filling to full size and colouring berry by berry through
	## veraison; overripe berries darken and shrivel.
	var sb: int = 100 + si * 80
	# Bunch size follows shoot vigour (+/-15%) on top of fill.
	var size_var: float = 0.85 + CR.hash_val(seed_val, sb + 5) * 0.3
	var length: float = CLUSTER_LENGTH * fill * size_var * emergence
	var radius: float = CLUSTER_RADIUS * fill * size_var * lerpf(0.5, 1.0, emergence)
	var ripe_c: Color = BERRY_RIPE.lerp(BERRY_DRY, senescence * 0.6)
	var bunch := Organs.build_bunch(length, radius, ripe_t, BERRY_GREEN, ripe_c, seed_val + si)
	# A bunch hangs from its origin and swings a little on its peduncle.
	var bunch_mat := CR.create_organ_material(
		Color.WHITE, 0.45, 0.5, CR.hash_val(seed_val, sb + 7) * TAU
	)
	var node_y: float = CLUSTER_NODE * (0.8 + CR.hash_val(seed_val, sb + 70) * 0.4)
	var z: float = (CR.hash_val(seed_val, sb + 6) - 0.5) * 0.06
	var ped_len: float = 0.03
	CR.attach_mesh(
		shoot,
		CR.create_stem_mesh(ped_len, 0.003, 0.003),
		CR.create_stem_material(senescence),
		Vector3(0, node_y - ped_len * 0.5, z * 0.5)
	)
	CR.attach_mesh(shoot, bunch, bunch_mat, Vector3(0, node_y - ped_len, z))
