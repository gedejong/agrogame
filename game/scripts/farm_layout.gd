class_name FarmLayout
extends RefCounted
## Maps a field's patch list onto the farm view's tile columns (#516).
##
## GET /games/{id} reports each field's patches in order. N patches become N
## contiguous column bands, and every tile keeps its band's patch_idx, so day
## results and per-patch actions map by index, never by soil name (two patches
## may share a soil).

## The field the farm view renders. Other fields are #472's.
const FIELD_ID := "field_1"
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


## Texture class for a soil preset key: "sand" gives sandy, "clay" gives clay,
## and anything else the middle ("organic") texture.
static func texture_for_soil_key(soil_profile_key: String) -> String:
	if soil_profile_key.contains("sand"):
		return "sandy"
	if soil_profile_key.contains("clay"):
		return "clay"
	return "organic"


## Give each tile its column band's patch_idx, and its material that patch's
## soil textures. An empty patch list leaves the tiles as they are.
static func assign_tiles(patches: Array, tile_data: Array, materials: Array, cols: int) -> void:
	if patches.is_empty():
		return
	for i in range(tile_data.size()):
		var patch_idx := patch_for_column(tile_data[i]["col"], patches.size(), cols)
		var soil_type := texture_for_soil_key(patches[patch_idx].get("soil_profile_key", ""))
		tile_data[i]["patch_idx"] = patch_idx
		tile_data[i]["soil_type"] = soil_type
		var paths: Dictionary = SOIL_TEXTURES[soil_type]
		materials[i].set_shader_parameter("albedo_texture", load(paths["albedo"]))
		materials[i].set_shader_parameter("normal_texture", load(paths["normal"]))


## FIELD_ID's patch list from a GET /games/{id} payload, or [] when absent.
static func patches_from_game(data: Dictionary) -> Array:
	var fields: Dictionary = data.get("fields", {})
	return fields.get(FIELD_ID, [])
