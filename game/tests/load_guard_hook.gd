extends GutHookScript
## Post-run guard against false-green CI (issue #338).
##
## GUT silently drops any test script that fails to *load* — parse errors,
## stale call signatures, or references to removed symbols. Those tests never
## run, yet the suite still exits 0. This hook compares the test files present
## on disk against the scripts GUT actually collected and forces a non-zero
## exit code (naming the offenders) whenever any script failed to load.

const TEST_DIRS: Array[String] = ["res://tests/unit/"]
const TEST_PREFIX := "test_"
const TEST_SUFFIX := ".gd"


func run() -> void:
	var expected: Array[String] = _find_test_files()
	var collected: Dictionary = _collected_paths()
	var missing: Array[String] = []
	for path in expected:
		if not collected.has(path):
			missing.append(path)
	missing.sort()

	if missing.is_empty():
		gut.logger.info("Load guard: all %d test scripts loaded." % expected.size())
		return

	gut.logger.error(
		(
			"Load guard: %d of %d test scripts failed to load — false green blocked."
			% [missing.size(), expected.size()]
		)
	)
	for path in missing:
		gut.logger.error("  did not load: %s" % path)
	set_exit_code(1)


func _collected_paths() -> Dictionary:
	var paths: Dictionary = {}
	var collector: Object = gut.get_test_collector()
	for script in collector.scripts:
		paths[script.path] = true
	return paths


func _find_test_files() -> Array[String]:
	var found: Array[String] = []
	for dir_path in TEST_DIRS:
		_scan_dir(dir_path, found)
	return found


func _scan_dir(path: String, found: Array[String]) -> void:
	var dir: DirAccess = DirAccess.open(path)
	if dir == null:
		gut.logger.error("Load guard: cannot open test dir %s" % path)
		set_exit_code(1)
		return
	dir.list_dir_begin()
	var entry: String = dir.get_next()
	while entry != "":
		var full: String = path.path_join(entry)
		if dir.current_is_dir():
			_scan_dir(full, found)
		elif entry.begins_with(TEST_PREFIX) and entry.ends_with(TEST_SUFFIX):
			found.append(full)
		entry = dir.get_next()
	dir.list_dir_end()
