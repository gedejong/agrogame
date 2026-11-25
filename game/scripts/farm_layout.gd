class_name FarmLayout
extends RefCounted
## Maps a game's fields onto the farm view's tile grid (#516, #600).
##
## GET /games/{id} reports every field's patches in order. Fields become
## contiguous row bands and, within a field, its N patches become N contiguous
## column bands. Every tile keeps its (field_id, patch_idx), so day results and
## per-patch actions map by that pair: never by soil name (two patches may share
## a soil), and never by patch index alone (every field has a patch 0).

## The z gap between two fields' row bands, in world units (a tile is 1.0). A
## visual boundary only: every field is modelled as 1 ha (#472 G1).
const FIELD_GAP := 0.3
## Albedo and normal maps per texture class (moved from farm_view.gd).
const SOIL_TEXTURES := {
	"sandy":
	{
		"albedo": "res://assets/textures/soil_sandy_albedo.png",
		"normal": "res://assets/textures/soil_sandy_normal.png",
	},
	"organic":
	{
		"albedo": "res://assets/textures/soil_loam_albedo.png",
		"normal": "res://assets/textures/soil_loam_normal.png",
	},
	"clay":
	{
		"albedo": "res://assets/textures/soil_clay_albedo.png",
		"normal": "res://assets/textures/soil_clay_normal.png",
	},
}


## Patch owning column `col` when `patch_count` patches share `cols` columns.
## On 6 columns: N=1 gives all 6, N=2 gives 3+3, N=3 gives 2+2+2.
static func patch_for_column(col: int, patch_count: int, cols: int) -> int:
	if patch_count <= 0 or cols <= 0:
		return 0
	return clampi(floori(float(col * patch_count) / float(cols)), 0, patch_count - 1)


## Field owning row `row` when `field_count` fields share `rows` rows: the
## column formula on rows, so on 6 rows 2 fields take 3+3 and 3 take 2+2+2.
static func field_for_row(row: int, field_count: int, rows: int) -> int:
	return patch_for_column(row, field_count, rows)


## Texture class for a soil preset key: "sand" gives sandy, "clay" gives clay,
## and anything else the middle ("organic") texture.
static func texture_for_soil_key(soil_profile_key: String) -> String:
	if soil_profile_key.contains("sand"):
		return "sandy"
	if soil_profile_key.contains("clay"):
		return "clay"
	return "organic"


## What to call a tile's soil: the preset's display name from the API ("Loam -
## Temperate"), else its texture class when the payload predates soil_name (#629).
static func soil_label(tile: Dictionary) -> String:
	var soil_name: String = tile.get("soil_name", "")
	return soil_name if not soil_name.is_empty() else tile.get("soil_type", "")


## Why `fields` cannot be laid out on `grid` (columns, rows), or "" when it can.
## Each field needs a row and each of its patches a column, so a layout that
## does not fit is refused whole rather than shown with a field missing.
static func layout_error(fields: Array, grid: Vector2i) -> String:
	if fields.size() > grid.y:
		return "%d fields, but the map has %d rows" % [fields.size(), grid.y]
	for field: Dictionary in fields:
		var count: int = (field["patches"] as Array).size()
		if count < 1 or count > grid.x:
			return "%s has %d patches; a field takes 1 to %d" % [field["field_id"], count, grid.x]
	return ""


## Give each tile its row band's field_id, that field's column band's
## patch_idx, and its material that patch's soil textures. `fields` is
## [{field_id, patches}] and must fit `grid` (layout_error). An empty field list
## leaves the tiles as they are.
static func assign_fields(
	fields: Array, tile_data: Array, materials: Array, grid: Vector2i
) -> void:
	if fields.is_empty():
		return
	for i in range(tile_data.size()):
		var tile: Dictionary = tile_data[i]
		var field: Dictionary = fields[field_for_row(tile.get("row", 0), fields.size(), grid.y)]
		var patches: Array = field["patches"]
		var patch_idx := patch_for_column(tile["col"], patches.size(), grid.x)
		var soil_type := texture_for_soil_key(patches[patch_idx].get("soil_profile_key", ""))
		tile["field_id"] = field["field_id"]
		tile["patch_idx"] = patch_idx
		tile["soil_type"] = soil_type
		tile["soil_name"] = patches[patch_idx].get("soil_name", "")
		tile["soil_profile_key"] = patches[patch_idx].get("soil_profile_key", "")
		tile["climate_key"] = patches[patch_idx].get("climate_key", "")
		var paths: Dictionary = SOIL_TEXTURES[soil_type]
		materials[i].set_shader_parameter("albedo_texture", load(paths["albedo"]))
		materials[i].set_shader_parameter("normal_texture", load(paths["normal"]))


## Each row's z when `field_count` fields share `rows` rows of `tile_size`:
## rows of one field tile_size apart, rows either side of a field boundary
## tile_size + FIELD_GAP apart, and the whole centred on z = 0. One field gives
## the plain grid's positions exactly.
static func row_z(field_count: int, rows: int, tile_size: float) -> Array[float]:
	var z: Array[float] = []
	var total := 0.0
	for row in range(rows):
		z.append(row * tile_size + FIELD_GAP * field_for_row(row, field_count, rows))
		total += z[row]
	var mean: float = total / float(maxi(rows, 1))
	for row in range(rows):
		z[row] -= mean
	return z


## The fields of a GET /games/{id} payload as [{field_id, patches}], in the
## payload's key order (the server's creation order), or [] when absent.
static func fields_from_game(data: Dictionary) -> Array:
	var fields: Dictionary = data.get("fields", {})
	var out: Array = []
	for field_id: String in fields:
		out.append({"field_id": field_id, "patches": fields[field_id]})
	return out


## The key history and stress icons file `field_id`'s patch `patch_idx` under.
static func patch_key(field_id: String, patch_idx: int) -> String:
	return "%s/%d" % [field_id, patch_idx]


## patch_key of the (field, patch) a tile is laid out as.
static func tile_key(tile: Dictionary) -> String:
	return patch_key(tile.get("field_id", ""), tile.get("patch_idx", -1))


## Indices, ascending, of the tiles laid out as `field_id`'s patch `patch_idx`.
static func tiles_of(field_id: String, patch_idx: int, tile_data: Array) -> Array[int]:
	var key := patch_key(field_id, patch_idx)
	var out: Array[int] = []
	for i in range(tile_data.size()):
		if tile_key(tile_data[i]) == key:
			out.append(i)
	return out
