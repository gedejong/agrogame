extends RefCounted
## Single-mesh builders for the reproductive organs of the crop renderers.
## Each organ is one ArrayMesh whatever its detail, so a plant stays at a
## handful of meshes: the baked stand path draws one MultiMesh per distinct
## mesh, and a tile of 400 wheat plants cannot afford a mesh per spikelet.
## Vertex colours are set on every vertex; materials that ignore them are
## unaffected, and a bunch reads its per-berry colour from them.

const CR = preload("res://scripts/crop_renderer_3d.gd")

## Golden angle (rad): successive spikelets of a spiral panicle.
const GOLDEN_ANGLE := 2.399963


static func build_spike(
	length: float,
	width: float,
	spikelets: int,
	awn_length: float,
	bend: float,
	spiral: bool,
	seed_val: int
) -> ArrayMesh:
	## Cereal head as one solid body along an axis rising from the origin
	## (+y) and turning by bend rad towards +z: a ripe head nods. The body
	## bulges once per spikelet, alternately left and right for a two-rowed
	## ear (wheat) or spiralling at the golden angle for a panicle (rice); at
	## field scale a head reads by its silhouette, so the packed spikelets are
	## drawn as that lumpy body, not one by one. Awns are thin quads leaning
	## out from the spikelets when awn_length > 0. Vertex colours shade the
	## grooves between spikelets darker (0.82-1.0 grey) for materials that
	## read them.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var n: int = maxi(spikelets, 1)
	var rings: int = n * 2 + 1
	var sectors: int = 6
	var prev: Array[Vector3] = []
	var prev_col := Color.WHITE
	for ri in range(rings + 1):
		var u: float = float(ri) / float(rings)
		var p: Vector3 = _axis_point(u, length, bend)
		var d: Vector3 = _axis_dir(u, bend)
		var e2: Vector3 = d.cross(Vector3.RIGHT).normalized()
		var k: float = u * float(n)
		var index: int = mini(floori(k), n - 1)
		var frac: float = k - float(index)
		var bulge: float = sin(PI * frac)
		var side: Vector3 = _spikelet_side(index, spiral, e2, seed_val)
		var centre: Vector3 = p + side * width * 0.18 * bulge
		var taper: float = _head_taper(u, spiral)
		var rx: float = width * 0.5 * (0.8 + 0.3 * bulge) * taper
		var rz: float = width * (0.38 if spiral else 0.3) * (0.85 + 0.2 * bulge) * taper
		var ring: Array[Vector3] = []
		for si in range(sectors):
			var phi: float = TAU * float(si) / float(sectors)
			ring.append(centre + Vector3.RIGHT * (cos(phi) * rx) + e2 * (sin(phi) * rz))
		var col := Color.from_hsv(0.0, 0.0, lerpf(0.82, 1.0, bulge))
		if ri > 0:
			for si in range(sectors):
				var sj: int = (si + 1) % sectors
				st.set_color(prev_col.lerp(col, 0.5))
				_add_quad(st, prev[si], prev[sj], ring[sj], ring[si])
		prev = ring
		prev_col = col
	if awn_length > 0.0:
		_add_awns(st, length, width, n, awn_length, bend, spiral, seed_val)
	st.generate_normals()
	return st.commit()


static func build_panicle_head(length: float, radius: float, seed_val: int) -> ArrayMesh:
	## Compact grain-sorghum panicle rising from the origin along +y: an
	## ovoid broadest above its middle, its surface roughened by the packed
	## spikelet clusters and speckled in vertex colour so the head reads as
	## grain rather than as a smooth bulb.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	_add_lumpy_body(
		st, Vector3.ZERO, Vector3.UP, length, radius, 0.16, seed_val, Color.WHITE, 12, 10, 0.6, 0.45
	)
	st.generate_normals()
	return st.commit()


static func build_bunch(
	length: float, radius: float, ripe_t: float, green: Color, ripe: Color, seed_val: int
) -> ArrayMesh:
	## Conical grape cluster hanging from the origin along -y: a dark core
	## sheathed in rows of berries whose count shrinks towards the tip.
	## Berries colour one by one through veraison: each has its own threshold
	## on ripe_t (0 all green, 1 all coloured), so a turning bunch is mottled.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var core: Color = green.lerp(ripe, ripe_t).darkened(0.45)
	_add_lumpy_body(
		st,
		Vector3(0, -length * 0.05, 0),
		Vector3.DOWN,
		length * 0.9,
		radius * 0.7,
		0.05,
		seed_val,
		core
	)
	var rows: int = 6
	var berry_r: float = radius * 0.36
	for k in range(rows):
		var f: float = float(k) / float(rows - 1)
		var y_row: float = -length * (0.08 + 0.84 * f)
		var rr: float = radius * (1.0 - 0.68 * f) * (0.88 if k == 0 else 1.0)
		var count: int = maxi(3, roundi(TAU * rr / (2.0 * berry_r)))
		var phase: float = CR.hash_val(seed_val, 400 + k) * TAU
		for j in range(count):
			var hi: int = 420 + k * 16 + j
			var a: float = TAU * float(j) / float(count) + phase
			var radial: float = rr * (0.85 + CR.hash_val(seed_val, hi) * 0.3)
			var pos := Vector3(
				cos(a) * radial,
				y_row + (CR.hash_val(seed_val, hi + 1) - 0.5) * berry_r * 0.8,
				sin(a) * radial
			)
			var r: float = berry_r * (0.85 + CR.hash_val(seed_val, hi + 2) * 0.3)
			var threshold: float = 0.3 + CR.hash_val(seed_val, hi + 3) * 0.45
			var turned: float = smoothstep(threshold - 0.12, threshold + 0.12, ripe_t)
			var color: Color = green.lerp(ripe, turned)
			color = color.lightened((CR.hash_val(seed_val, hi + 4) - 0.5) * 0.16)
			_add_sphere(st, pos, r, color)
	st.generate_normals()
	return st.commit()


static func _axis_point(u: float, length: float, bend: float) -> Vector3:
	## Point at arc-length fraction u along an axis of constant curvature that
	## leaves the origin along +y and turns by bend rad towards +z overall.
	var s: float = u * length
	if absf(bend) < 1e-4:
		return Vector3(0.0, s, 0.0)
	var k: float = bend / length
	return Vector3(0.0, sin(k * s) / k, (1.0 - cos(k * s)) / k)


static func _axis_dir(u: float, bend: float) -> Vector3:
	return Vector3(0.0, cos(bend * u), sin(bend * u))


static func _add_lumpy_body(
	st: SurfaceTool,
	base: Vector3,
	axis: Vector3,
	length: float,
	radius: float,
	lumps: float,
	seed_val: int,
	color: Color,
	rings: int = 7,
	sectors: int = 8,
	peak: float = 0.5,
	speckle: float = 0.0
) -> void:
	## Body of revolution from base along axis, closed at both ends, broadest
	## at fraction peak of its length. Its radius is modulated by
	## low-frequency bumps of relative amplitude lumps, and each facet is
	## darkened by up to the fraction speckle of its colour so a fine mesh
	## reads as a granular surface.
	var side: Vector3 = Vector3.RIGHT if absf(axis.x) < 0.9 else Vector3.FORWARD
	var e1: Vector3 = axis.cross(side).normalized()
	var e2: Vector3 = axis.cross(e1).normalized()
	var ph1: float = CR.hash_val(seed_val, 500) * TAU
	var ph2: float = CR.hash_val(seed_val, 501) * TAU
	var prev: Array[Vector3] = []
	for ri in range(rings + 1):
		var v: float = float(ri) / float(rings)
		# Remap so the widest ring sits at v == peak.
		var w: float = v / peak * 0.5 if v < peak else 0.5 + (v - peak) / (1.0 - peak) * 0.5
		var ring: Array[Vector3] = []
		for si in range(sectors):
			var phi: float = TAU * float(si) / float(sectors)
			var bump: float = (
				0.5 * sin(v * 9.0 + phi * 3.0 + ph1) + 0.5 * sin(v * 15.0 - phi * 2.0 + ph2)
			)
			var rr: float = radius * pow(sin(PI * w), 0.65) * (1.0 + lumps * bump)
			ring.append(base + axis * (length * v) + (e1 * cos(phi) + e2 * sin(phi)) * rr)
		if ri > 0:
			for si in range(sectors):
				var sj: int = (si + 1) % sectors
				var shade: float = 1.0 - CR.hash_val(seed_val, 600 + ri * sectors + si) * speckle
				st.set_color(Color(color.r * shade, color.g * shade, color.b * shade, color.a))
				_add_quad(st, prev[si], prev[sj], ring[sj], ring[si])
		prev = ring


static func _spikelet_side(index: int, spiral: bool, e2: Vector3, seed_val: int) -> Vector3:
	## Direction in which spikelet index bulges out of the head: alternating
	## across the rows for a two-rowed ear, spiralling for a panicle, with a
	## little scatter either way.
	var angle: float
	if spiral:
		angle = float(index) * GOLDEN_ANGLE + CR.hash_val(seed_val, 300 + index) * 0.6
	else:
		angle = (PI if index % 2 == 1 else 0.0) + (CR.hash_val(seed_val, 300 + index) - 0.5) * 0.35
	return Vector3.RIGHT * cos(angle) + e2 * sin(angle)


static func _head_taper(u: float, spiral: bool) -> float:
	## Width profile along a head: a two-rowed ear is nearly parallel-sided
	## and blunt, a panicle is thin where its branches leave the peduncle and
	## broadest through its middle. Zero at both ends closes the body.
	if spiral:
		return smoothstep(0.0, 0.3, u) * (1.0 - smoothstep(0.7, 1.0, u))
	var shoulder: float = 1.0 - 0.4 * smoothstep(0.6, 0.92, u)
	return smoothstep(0.0, 0.1, u) * shoulder * (1.0 - smoothstep(0.92, 1.0, u))


static func _add_awns(
	st: SurfaceTool,
	length: float,
	width: float,
	n: int,
	awn_length: float,
	bend: float,
	spiral: bool,
	seed_val: int
) -> void:
	## One awn per spikelet: a thin quad leaving the spikelet's flank and
	## leaning out from the axis, longer towards the tip of the head.
	st.set_color(Color.WHITE)
	for i in range(n):
		var u: float = (float(i) + 0.5) / float(n)
		var p: Vector3 = _axis_point(u, length, bend)
		var d: Vector3 = _axis_dir(u, bend)
		var e2: Vector3 = d.cross(Vector3.RIGHT).normalized()
		var side: Vector3 = _spikelet_side(i, spiral, e2, seed_val)
		var root: Vector3 = p + side * width * 0.5
		var splay: float = (CR.hash_val(seed_val, 360 + i) - 0.5) * 0.3
		var awn_dir: Vector3 = (d * 0.8 + side * (0.35 + splay)).normalized()
		var awn_len: float = awn_length * (0.75 + CR.hash_val(seed_val, 390 + i) * 0.5)
		var flat: Vector3 = d.cross(side).normalized()
		var aw: float = width * 0.09
		_add_quad(
			st,
			root - flat * aw,
			root + flat * aw,
			root + awn_dir * awn_len + flat * aw * 0.3,
			root + awn_dir * awn_len - flat * aw * 0.3
		)


static func _add_sphere(st: SurfaceTool, centre: Vector3, r: float, color: Color) -> void:
	## Low-poly sphere (3 latitude bands, 5 sectors): a berry.
	var rings: int = 3
	var sectors: int = 5
	var prev: Array[Vector3] = []
	for ri in range(rings + 1):
		var theta: float = PI * float(ri) / float(rings)
		var ring: Array[Vector3] = []
		for si in range(sectors):
			var phi: float = TAU * float(si) / float(sectors)
			ring.append(
				centre + Vector3(sin(theta) * cos(phi), cos(theta), sin(theta) * sin(phi)) * r
			)
		if ri > 0:
			for si in range(sectors):
				var sj: int = (si + 1) % sectors
				st.set_color(color)
				_add_quad(st, prev[si], prev[sj], ring[sj], ring[si])
		prev = ring


static func _add_quad(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, d: Vector3) -> void:
	## Two triangles (a, b, c), (a, c, d); degenerate triangles are dropped so
	## poles and collapsed edges never feed zero-area faces to normal generation.
	_add_tri(st, a, b, c)
	_add_tri(st, a, c, d)


static func _add_tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3) -> void:
	if (b - a).cross(c - a).length_squared() < 1e-14:
		return
	st.add_vertex(a)
	st.add_vertex(b)
	st.add_vertex(c)
