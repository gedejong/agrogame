class_name DioramaRegions
extends RefCounted
## The decorative extension's regional layers (#652, ADR-022 decision 1): below
## the simulated profile, one continuous stack per climate key, independent of
## the fields above, so no face shows a break at a segment join. No simulation
## value drives it. Depths are metres below the surface and are style constants
## within the cited setting; hue and chroma come from the CC0 sets, unedited.

const SHADER := preload("res://shaders/soil_extension.gdshader")
## Layer slots in the shader; slot MAX_LAYERS holds the artefact set.
const MAX_LAYERS := 4
## Below every layer's bottom: a bottom of INF runs to the slab's bottom.
const DEEP_M := 1.0e6
## Per climate key, top down, each layer as [name, top m, bottom m, set,
## artefact]. A first layer's top of 0 runs up to the simulated section, which
## covers it; a bottom of INF runs to the slab's bottom. The artefact is the
## DioramaArtefacts kind placed in that layer ("" for none).
const STACKS := {
	# The polder. TNO-GDN, Stratigraphic Nomenclature of the Netherlands: the
	# Naaldwijk Formation ("grey to blue silt and clay layers") over the
	# Nieuwkoop Formation's Basisveen Bed (the peat at its base), over the
	# Boxtel Formation's periglacial sand, with gravel lenses.
	"netherlands_temperate":
	[
		["Holocene marine clay", 0.0, 2.2, "brown_mud", ""],
		["Basal peat", 2.2, 2.8, "mud_forest", ""],
		["Pleistocene cover sand", 2.8, INF, "sand_01", "lens"],
	],
	# IUSS Working Group WRB (2022), World Reference Base, 4th ed., Nitisols;
	# Sombroek, Braun & van der Pouw (1982), Exploratory Soil Map of Kenya,
	# Kenya Soil Survey Report E1. Saprolite with corestones: Taylor &
	# Eggleton (2001), Regolith Geology and Geomorphology, Wiley.
	"kenya_highlands":
	[
		["Red clay subsoil (nitic)", 0.0, 2.6, "red_mud_stones", ""],
		["Saprolite of weathered volcanic rock", 2.6, INF, "rock_face", "corestone"],
	],
	# WRB (2022): Arenosols, pisoplinthic and petroplinthic horizons. Tardy
	# (1997), Petrology of Laterites and Tropical Soils, Balkema: ferricrete
	# over the mottled and pallid zones. No site-specific claim.
	"sahel_arid":
	[
		["Aeolian sand", 0.0, 1.6, "gravelly_sand", "lens"],
		["Ironstone gravel", 1.6, 2.2, "red_laterite_soil_stones", ""],
		["Ferricrete", 2.2, 2.8, "rock_face", ""],
		["Mottled and pallid zone", 2.8, INF, "dense_sand", ""],
	],
}
## The set each region's artefacts are drawn with: river-gravel lenses in the
## Dutch sand, weathered boulders for the corestones in the Kenyan saprolite,
## and in the Sahel sand lenses of the ironstone gravel below it. (Swapped in
## PR #682's review: the refined rock_wall_08 put masonry joints inside the
## corestones, and sandy_gravel read as smears.)
const ARTEFACT_SET := {
	"netherlands_temperate": "dry_river_pebbles",
	"kenya_highlands": "rock_boulder_dry",
	"sahel_arid": "red_laterite_soil_stones",
}
## Side of each set's scanned square, m: Poly Haven API /info/<id>,
## "dimensions" in mm, read 2026-11-25.
const SET_SIZE_M := {
	"brown_mud": 1.30,
	"mud_forest": 2.35,
	"sand_01": 1.50,
	"red_mud_stones": 1.50,
	"rock_face": 2.38,
	"gravelly_sand": 2.48,
	"red_laterite_soil_stones": 2.00,
	"dense_sand": 1.80,
	"rock_boulder_dry": 1.80,
	"dry_river_pebbles": 2.00,
}


## The layers under `climate_key`, top down, each {name, top_m, bottom_m, set,
## size_m, artefact}; empty for an unknown key.
static func layers_for(climate_key: String) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	for row: Array in STACKS.get(climate_key, []):
		var keys := ["name", "top_m", "bottom_m", "set", "artefact"]
		var layer := {}
		for i in range(keys.size()):
			layer[keys[i]] = row[i]
		layer["size_m"] = SET_SIZE_M[row[3]]
		out.append(layer)
	return out


## The path of `set`'s `map` ("diff", "nor_gl" or "arm").
static func map_path(set_id: String, map: String) -> String:
	return "res://assets/materials/%s/%s_%s.jpg" % [set_id, set_id, map]


## The extension material for `climate_key`, null for an unknown key. The slab
## fills in the depth-dependent parameters (DioramaArtefacts.fit).
static func material(climate_key: String, wu_per_m: float) -> ShaderMaterial:
	var layers := layers_for(climate_key)
	if layers.is_empty():
		return null
	var sets: Array[String] = []
	var bottoms := PackedFloat32Array()
	for i in range(MAX_LAYERS):
		var layer: Dictionary = layers[mini(i, layers.size() - 1)]
		sets.append(layer["set"])
		if i < MAX_LAYERS - 1:
			bottoms.append(minf(layer["bottom_m"], DEEP_M) if i < layers.size() else DEEP_M)
	sets.append(ARTEFACT_SET[climate_key])
	var mat := ShaderMaterial.new()
	mat.shader = SHADER
	for map: String in ["diff", "nor_gl", "arm"]:
		var textures: Array[Texture2D] = []
		for set_id: String in sets:
			textures.append(load(map_path(set_id, map)))
		mat.set_shader_parameter("set_" + map, textures)
	mat.set_shader_parameter("set_size_m", PackedFloat32Array(sets.map(_size)))
	mat.set_shader_parameter("layer_bottom_m", bottoms)
	mat.set_shader_parameter("wu_per_m", wu_per_m)
	return mat


static func _size(set_id: String) -> float:
	return SET_SIZE_M[set_id]
