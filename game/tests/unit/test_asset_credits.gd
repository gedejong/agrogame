extends GutTest
## Downloaded assets (#652, ADR-022 decision 5): every file under
## game/assets/materials/ and game/assets/models/ loads, and has a CREDITS.md
## row with an allowed licence; every row names a file that exists. A Git LFS
## pointer in place of a binary fails with the fix.

const ROOTS := ["res://assets/materials", "res://assets/models"]
const CREDITS := "res://assets/CREDITS.md"
const LFS_POINTER := "version https://git-lfs.github.com/spec/v1"
## Licences besides CC0 1.0 that Edwin approved (ADR-022 decision 5: anything
## else needs his approval first), each with the date and issue. None yet.
const APPROVED_LICENCES := {}


## Every file under `dir`, recursively, without Godot's .import and .uid files.
func _files(dir: String) -> Array[String]:
	var out: Array[String] = []
	var da := DirAccess.open(dir)
	if da == null:
		return out
	for sub: String in da.get_directories():
		out.append_array(_files(dir.path_join(sub)))
	for file: String in da.get_files():
		if file.get_extension() not in ["import", "uid"]:
			out.append(dir.path_join(file))
	return out


## CREDITS.md rows as {res:// path: licence}: the first and fourth columns.
func _credits(text: String) -> Dictionary:
	var rows := {}
	for line: String in text.split("\n"):
		var cells := line.split("|")
		if cells.size() > 5 and cells[1].strip_edges().begins_with("`"):
			var path := "res://assets/" + cells[1].strip_edges().trim_prefix("`").trim_suffix("`")
			rows[path] = cells[4].strip_edges()
	return rows


## What is wrong with `files` against `rows`; `head` returns a file's first bytes
## as text and `loads` whether it loads as a Texture2D or PackedScene.
func _problems(files: Array[String], rows: Dictionary, head: Callable, loads: Callable) -> Array:
	var out := []
	for path: String in files:
		if (head.call(path) as String).begins_with(LFS_POINTER):
			out.append("%s is a Git LFS pointer: run `git lfs pull`" % path)
		elif not loads.call(path):
			out.append("%s does not load as Texture2D or PackedScene" % path)
		if not rows.has(path):
			out.append("%s has no CREDITS.md row" % path)
		elif rows[path] != "CC0 1.0" and not APPROVED_LICENCES.has(rows[path]):
			out.append("%s: licence %s is not approved" % [path, rows[path]])
	for path: String in rows:
		if path not in files:
			out.append("CREDITS.md row %s has no file" % path)
	return out


func _head(path: String) -> String:
	var f := FileAccess.open(path, FileAccess.READ)
	return f.get_buffer(LFS_POINTER.length()).get_string_from_ascii() if f else ""


func _loads(path: String) -> bool:
	var res := load(path)
	return res is Texture2D or res is PackedScene


func test_every_asset_loads_and_is_credited() -> void:
	var files: Array[String] = []
	for dir: String in ROOTS:
		files.append_array(_files(dir))
	assert_gte(files.size(), 30, "ten sets of albedo, normal and ARM maps")
	var rows := _credits(FileAccess.get_file_as_string(CREDITS))
	assert_eq(_problems(files, rows, _head, _loads), [])


func test_materials_are_512_px() -> void:
	for path: String in _files(ROOTS[0]):
		var tex := load(path) as Texture2D
		if tex != null:  # a file that does not load fails the credits test
			assert_eq(tex.get_size(), Vector2(512, 512), path)


func test_a_missing_row_an_orphan_row_a_pointer_and_a_licence_fail() -> void:
	var pointer := "user://lfs_pointer.jpg"
	var f := FileAccess.open(pointer, FileAccess.WRITE)
	f.store_string(LFS_POINTER + "\noid sha256:0\nsize 1\n")
	f.close()
	var credited := "res://assets/materials/brown_mud/brown_mud_diff.jpg"
	var files: Array[String] = [credited, pointer, "res://icon.svg"]
	var rows := {credited: "CC0 1.0", "res://assets/gone.jpg": "CC0 1.0", pointer: "CC-BY 4.0"}
	var got := _problems(files, rows, _head, _loads)
	assert_eq(got.size(), 4, str(got))
	assert_string_contains(got[0], "git lfs pull")
	assert_string_contains(got[1], "licence CC-BY 4.0 is not approved")
	assert_string_contains(got[2], "icon.svg has no CREDITS.md row")
	assert_string_contains(got[3], "gone.jpg has no file")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(pointer))
