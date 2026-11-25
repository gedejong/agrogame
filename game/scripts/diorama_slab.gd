class_name DioramaSlab
extends Node3D
## The diorama slab (#646, ADR-022 decision 1): each field band is a finite
## block whose two camera-facing cut faces show the soil beneath the surface.
##
## One face segment per edge tile, +x under the last column of every row and
## +z under each field band's last row, mapped to its patch through the tile's
## (field_id, patch_idx) (#600). The simulated section is drawn at true scale,
## as deep as the deepest profile in the payload; below it a decorative
## extension, one quad per field block and side, reaches EXTENSION_FACTOR
## times that depth. The -x, -z and bottom sides are closed and plain. No face
## has a collision shape, so clicks still reach the tiles.

const FACE_SHADER := preload("res://shaders/soil_face.gdshader")
## 1 cm in world units: a tile is 1 wu and METERS_PER_TILE (farm_view.gd) 2 m.
const WU_PER_CM := 0.005
## Total depth over the simulated section's. Edwin's range is 4 to 8 (ADR-022);
## 4 is the deepest whose bottom corner stays above the BottomBar (#646).
const EXTENSION_FACTOR := 4.0
## Albedo of the closed sides, seen only under the debug orbit (style, sRGB).
const SIDE_COLOUR := Color(0.24, 0.19, 0.15)
## Seed of the extension's artefact placement (#652): fixed, so a farm's stones
## and lenses stay put from day to day and across reloads.
const ARTEFACT_SEED := 652

## The cross-section textures with mipmaps, built once (_grain_textures).
static var _grains: Array[Texture2D] = []

## Each {mesh, side ("+x" or "+z"), field_id, patch_idx, tile (col, row)}; the
## mesh carries its own ShaderMaterial as material_override.
var _segments: Array[Dictionary] = []
## Each {mesh, width, placeholder, keys}: keys[i] is the patch key of the
## segment above slot i along the quad's UV.x; placeholder its own material.
var _extensions: Array[Dictionary] = []
## Each {mesh, width, depth}: closed -x and -z sides (depth 0: the whole slab)
## and bottoms (depth: their z extent).
var _sides: Array[Dictionary] = []
var _corner := Vector2.ZERO  # the front corner's (x, z)
var _section_cm := 0.0
var _extension_material: Material = null
var _segment_mesh := QuadMesh.new()
## The layout's climate key and its regional extension material (#652; null
## for an unknown key), and the extension's span along the unfolded face (wu).
var _climate := ""
var _regional: ShaderMaterial = null
var _u_span := Vector2(INF, -INF)
var _soil_keys := {}  # patch key -> its PRESET_LCH key (#680)


## Build the faces for `fields` laid out on `tile_data` / `tile_meshes`. The
## scene's lights alone light them, with no fill on the face turned from the sun
## (Edwin, 2026-11-25; #680). Faces stay hidden until update() sizes them.
func lay_out(fields: Array, tile_data: Array, tile_meshes: Array) -> void:
	for child: Node in get_children():
		child.free()
	_segments.clear()
	_extensions.clear()
	_sides.clear()
	_section_cm = 0.0
	_climate = _climate_key(fields)
	_regional = DioramaRegions.material(_climate, WU_PER_CM * 100.0)
	_extension_material = null
	_u_span = Vector2(INF, -INF)
	var last_col := 0
	for tile: Dictionary in tile_data:
		last_col = maxi(last_col, tile["col"])
	_corner = Vector2(-INF, -INF)
	for field: Dictionary in fields:
		var tiles: Array[int] = []
		var lo := Vector2(INF, INF)
		var hi := Vector2(-INF, -INF)
		for i in range(tile_data.size()):
			if tile_data[i].get("field_id", "") == field["field_id"]:
				var p: Vector3 = (tile_meshes[i] as Node3D).position
				lo = lo.min(Vector2(p.x - 0.5, p.z - 0.5))
				hi = hi.max(Vector2(p.x + 0.5, p.z + 0.5))
				tiles.append(i)
		if not tiles.is_empty():
			_corner = _corner.max(hi)
			_lay_out_block(tiles, tile_data, tile_meshes, last_col, Rect2(lo, hi - lo))
	_resize()


## Replace the extension placeholder with `material` (#652's regional content)
## on every extension quad; null restores the placeholder.
func set_extension_material(material: Material) -> void:
	_extension_material = material
	for ext: Dictionary in _extensions:
		(ext["mesh"] as MeshInstance3D).material_override = _extension(ext)


## Redraw every laid-out patch's faces from a /step result's `patches`
## ({field_id: [patch, ...]}). A patch without a profile keeps its faces hidden.
func update(patches: Dictionary) -> void:
	var states := {}
	var deepest := 0.0
	for seg: Dictionary in _segments:
		var plist: Array = patches.get(seg["field_id"], [])
		if seg["patch_idx"] < 0 or seg["patch_idx"] >= plist.size():
			continue
		var patch: Dictionary = plist[seg["patch_idx"]]
		var soil: Variant = patch.get("soil_state")
		if soil is Dictionary and SoilFaceColour.has_profile(soil):
			states[_key(seg)] = patch
			deepest = maxf(deepest, SoilFaceColour.profile_depth_cm(soil))
	if states.is_empty():
		return
	if deepest != _section_cm:
		_section_cm = deepest
		_resize()
		_fit_regional()
	var textures := {}
	var hues := {}
	for seg: Dictionary in _segments:
		_soil_keys[_key(seg)] = seg["soil_key"]
	for key: String in states:
		var patch: Dictionary = states[key]
		var root_cm: float = patch.get("root_depth_cm", 0.0)
		var cells := SoilFaceColour.samples(patch["soil_state"], root_cm, _section_cm)
		textures[key] = _texture(cells, 1, cells.size())
		var tint := SoilFaceColour.hue_samples(patch["soil_state"], _soil_keys[key], _section_cm)
		hues[key] = _texture(tint, 1, tint.size())
	for seg: Dictionary in _segments:
		if textures.has(_key(seg)):
			var mesh: MeshInstance3D = seg["mesh"]
			var mat: ShaderMaterial = mesh.material_override
			mat.set_shader_parameter("profile_tex", textures[_key(seg)])
			mat.set_shader_parameter("hue_tex", hues[_key(seg)])
			mesh.visible = true
	for ext: Dictionary in _extensions:
		_update_placeholder(ext, states)  # kept current for set_extension_material(null)
		(ext["mesh"] as MeshInstance3D).visible = true
	for side: Dictionary in _sides:
		(side["mesh"] as MeshInstance3D).visible = true


## The simulated section's depth in world units (0 before the first payload).
func section_depth_wu() -> float:
	return _section_cm * WU_PER_CM


## The slab's whole depth, section plus extension, in world units.
func total_depth_wu() -> float:
	return section_depth_wu() * EXTENSION_FACTOR


## The slab's lowest front corner, under the +x and +z faces.
func front_corner() -> Vector3:
	return Vector3(_corner.x, -total_depth_wu(), _corner.y)


## One field block over `block` (x, z): segments and extensions on +x and +z,
## closed -x, -z and bottom.
func _lay_out_block(
	tiles: Array[int], tile_data: Array, tile_meshes: Array, last_col: int, block: Rect2
) -> void:
	var lo := block.position
	var hi := block.end
	var mid := block.get_center()
	var plus_x := _quad(Vector3(hi.x, 0.0, mid.y), Vector3(0.0, 90.0, 0.0))
	var plus_z := _quad(Vector3(mid.x, 0.0, hi.y), Vector3.ZERO)
	var on_x: Array[String] = []
	var on_z: Array[String] = []
	on_x.resize(roundi(block.size.y))
	on_z.resize(roundi(block.size.x))
	for i: int in tiles:
		var p: Vector3 = (tile_meshes[i] as Node3D).position
		if tile_data[i]["col"] == last_col:
			on_x[_slot(plus_x, p, on_x.size())] = _add_segment(
				Vector3(hi.x, 0.0, p.z), 90.0, tile_data[i]
			)
		if is_equal_approx(p.z + 0.5, hi.y):
			on_z[_slot(plus_z, p, on_z.size())] = _add_segment(
				Vector3(p.x, 0.0, hi.y), 0.0, tile_data[i]
			)
	_add_extension(plus_x, block.size.y, on_x)
	_add_extension(plus_z, block.size.x, on_z)
	_add_side(Vector3(lo.x, 0.0, mid.y), Vector3(0.0, -90.0, 0.0), block.size.y, 0.0)
	_add_side(Vector3(mid.x, 0.0, lo.y), Vector3(0.0, 180.0, 0.0), block.size.x, 0.0)
	_add_side(Vector3(mid.x, 0.0, mid.y), Vector3(90.0, 0.0, 0.0), block.size.x, block.size.y)


## A hidden, shadowless quad at `pos`, turned `rot` degrees; its outward
## normal is its +z axis.
func _quad(pos: Vector3, rot: Vector3, mesh: Mesh = QuadMesh.new()) -> MeshInstance3D:
	var quad := MeshInstance3D.new()
	quad.mesh = mesh
	quad.position = pos
	quad.rotation_degrees = rot
	quad.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	quad.visible = false
	add_child(quad)
	return quad


func _add_segment(pos: Vector3, rot_y: float, tile: Dictionary) -> String:
	var mesh := _quad(pos, Vector3(0.0, rot_y, 0.0), _segment_mesh)
	mesh.material_override = _face_material()
	var seg := {
		"mesh": mesh,
		"side": "+x" if rot_y > 0.0 else "+z",
		"field_id": tile["field_id"],
		"patch_idx": tile["patch_idx"],
		"soil_key": SoilFaceColour.colour_key(tile),
		"tile": Vector2i(tile["col"], tile["row"]),
	}
	_segments.append(seg)
	return _key(seg)


func _add_extension(mesh: MeshInstance3D, width: float, keys: Array[String]) -> void:
	var ext := {"mesh": mesh, "width": width, "placeholder": _face_material(), "keys": keys}
	_extensions.append(ext)
	mesh.material_override = _extension(ext)
	var u := mesh.position.x - mesh.position.z  # the shader's unfolded face
	_u_span = Vector2(minf(_u_span.x, u - width / 2.0), maxf(_u_span.y, u + width / 2.0))


func _add_side(pos: Vector3, rot: Vector3, width: float, depth: float) -> void:
	var mesh := _quad(pos, rot)
	var plain := StandardMaterial3D.new()
	plain.albedo_color = SIDE_COLOUR
	mesh.material_override = plain
	_sides.append({"mesh": mesh, "width": width, "depth": depth})


## Complete the regional material from the section's depth, where its first
## layer and its artefacts start, and put it on the extension unless the hook
## already holds a material (#652).
func _fit_regional() -> void:
	if _regional == null:
		return
	var bottom_m := _section_cm / 100.0
	var span_m := _u_span / (WU_PER_CM * 100.0)
	var placed := DioramaArtefacts.place(
		_climate, ARTEFACT_SEED, bottom_m, bottom_m * EXTENSION_FACTOR, span_m
	)
	_regional.set_shader_parameter("profile_bottom_m", bottom_m)
	_regional.set_shader_parameter("artefacts", DioramaArtefacts.texture(placed))
	_regional.set_shader_parameter("artefact_count", placed.size())
	if _extension_material == null:
		set_extension_material(_regional)


func _extension(ext: Dictionary) -> Material:
	return _extension_material if _extension_material != null else ext["placeholder"]


## The placeholder's strip: under each segment, its patch's deepest layer.
func _update_placeholder(ext: Dictionary, states: Dictionary) -> void:
	var cells := PackedColorArray()
	var tints := PackedColorArray()
	for key: String in ext["keys"]:
		var cell := Color(0.0, 0.0, 0.0, 1.0)
		var tint := Color.WHITE
		if states.has(key):
			var soil: Dictionary = states[key]["soil_state"]
			var last: int = (soil["texture"] as Array).size() - 1
			var col := SoilFaceColour.column(soil["texture"][last])
			cell = Color(SoilFaceColour.layer_scale(soil, last), 0.0, col / 2.0, 1.0)
			var g := SoilFaceColour.face_gain(soil, _soil_keys.get(key, ""), last)
			tint = Color(g.x, g.y, g.z, 1.0)
		cells.append(cell)
		tints.append(tint)
	var placeholder: ShaderMaterial = ext["placeholder"]
	placeholder.set_shader_parameter("profile_tex", _texture(cells, cells.size(), 1))
	placeholder.set_shader_parameter("hue_tex", _texture(tints, tints.size(), 1))


## Slot along `quad`'s UV.x, of `count` one-tile slots, of the tile at `p`.
func _slot(quad: MeshInstance3D, p: Vector3, count: int) -> int:
	var local_x := (quad.transform.affine_inverse() * p).x
	return clampi(floori(local_x + count / 2.0), 0, count - 1)


func _face_material() -> ShaderMaterial:
	var mat := ShaderMaterial.new()
	mat.shader = FACE_SHADER
	var grains := _grain_textures()
	mat.set_shader_parameter("grain_sandy", grains[0])
	mat.set_shader_parameter("grain_loam", grains[1])
	mat.set_shader_parameter("grain_clay", grains[2])
	return mat


## Size every face to the section: segments from y = 0 down the section,
## extensions below it to the whole depth, -x and -z over the whole depth, and
## the bottoms at its foot.
func _resize() -> void:
	var h := section_depth_wu()
	var total := total_depth_wu()
	_segment_mesh.size = Vector2(1.0, h)
	_segment_mesh.center_offset = Vector3(0.0, -h / 2.0, 0.0)
	for ext: Dictionary in _extensions:
		var quad: QuadMesh = (ext["mesh"] as MeshInstance3D).mesh
		quad.size = Vector2(ext["width"], total - h)
		quad.center_offset = Vector3(0.0, -(h + total) / 2.0, 0.0)
	for side: Dictionary in _sides:
		var mesh: MeshInstance3D = side["mesh"]
		var quad: QuadMesh = mesh.mesh
		if side["depth"] > 0.0:
			quad.size = Vector2(side["width"], side["depth"])
			mesh.position.y = -total
		else:
			quad.size = Vector2(side["width"], total)
			quad.center_offset = Vector3(0.0, -total / 2.0, 0.0)


## The climate key the layout's patches carry (create_game rejects mixed
## climates); "" without one.
static func _climate_key(fields: Array) -> String:
	for field: Dictionary in fields:
		for patch: Dictionary in field.get("patches", []):
			return patch.get("climate_key", "")
	return ""


static func _key(seg: Dictionary) -> String:
	return FarmLayout.patch_key(seg["field_id"], seg["patch_idx"])


## An RGBA float texture of `cells`, `width` by `height`, row-major.
static func _texture(cells: PackedColorArray, width: int, height: int) -> ImageTexture:
	var img := Image.create(width, height, false, Image.FORMAT_RGBAF)
	for i in range(cells.size()):
		img.set_pixel(i % width, floori(float(i) / width), cells[i])
	return ImageTexture.create_from_image(img)


## The cross-section textures (S, L, C) with mipmaps, built once.
static func _grain_textures() -> Array[Texture2D]:
	if _grains.is_empty():
		for path: String in SoilFaceColour.CROSS_TEXTURES:
			var img := (load(path) as Texture2D).get_image()
			img.generate_mipmaps()
			_grains.append(ImageTexture.create_from_image(img))
	return _grains
