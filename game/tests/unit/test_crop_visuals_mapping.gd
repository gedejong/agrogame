extends GutTest
## Stage / development-stage -> renderer-input mapping in CropVisuals.

const VisualsRef = preload("res://scripts/crop_visuals.gd")


func test_calc_repro_zero_before_heading() -> void:
	assert_eq(VisualsRef._calc_repro(0, 0.0), 0.0)
	assert_eq(VisualsRef._calc_repro(1, 0.0), 0.0)
	assert_eq(VisualsRef._calc_repro(2, 0.0, 0.5), 0.0)
	# A vegetative crop is capped just short of anthesis however far its
	# thermal time has run (unmet vernalization / photoperiod).
	assert_lt(VisualsRef._calc_repro(2, 0.0, 1.5), 0.1)


func test_calc_repro_rises_through_grain_fill() -> void:
	var flowering: float = VisualsRef._calc_repro(3, 0.0, 1.05)
	var filling: float = VisualsRef._calc_repro(4, 0.5, 1.5)
	var mature: float = VisualsRef._calc_repro(4, 1.0, 2.0)
	assert_gt(flowering, 0.0, "Heading precedes anthesis")
	assert_gt(filling, flowering)
	assert_almost_eq(mature, 1.0, 0.001)


func test_calc_repro_nominal_without_dev_stage() -> void:
	assert_gt(VisualsRef._calc_repro(3, 0.0), 0.0, "Flowering implies heading")
	assert_gt(VisualsRef._calc_repro(4, 1.0), VisualsRef._calc_repro(4, 0.0))


func test_nominal_dev_stage_monotonic() -> void:
	var prev: float = -1.0
	for stage in range(5):
		var dvs: float = VisualsRef._nominal_dev_stage(stage, 0.5)
		assert_gt(dvs, prev, "DVS increases with stage %d" % stage)
		prev = dvs
	assert_almost_eq(VisualsRef._nominal_dev_stage(4, 1.0), 2.0, 0.001)


func test_growth_keeps_stature_after_canopy_peak() -> void:
	# Grain fill sheds leaf area, not stem: size follows the season peak.
	var at_peak: float = VisualsRef._calc_growth(4, 0.75, 0.5, 1.5, 0.75)
	var declining: float = VisualsRef._calc_growth(4, 0.25, 0.8, 1.8, 0.75)
	assert_almost_eq(declining, at_peak, 0.001)


func test_dev_stage_drives_elongation_at_low_lai() -> void:
	# A sparse but developmentally advanced crop has still bolted.
	var early: float = VisualsRef._calc_growth(2, 0.1, 0.0, 0.2)
	var late: float = VisualsRef._calc_growth(2, 0.1, 0.0, 0.9)
	assert_gt(late, early)
	assert_lt(late, 0.75, "Elongation alone never reaches full size")


func test_senescence_measured_against_lai_peak() -> void:
	# The same LAI reads as more senescent when the season peak was higher.
	var low_peak: float = VisualsRef._calc_senescence(4, 2.0, 0.5, 1.5, 3.0)
	var high_peak: float = VisualsRef._calc_senescence(4, 2.0, 0.5, 1.5, 6.0)
	assert_gt(high_peak, low_peak)


func test_ripening_senescence_weight_stay_green() -> void:
	# At maturity with an intact canopy maize yellows fully; grape leaves
	# stay green while the fruit ripens (ripening weight 0).
	var maize: float = VisualsRef._calc_senescence(4, 4.5, 1.0, 2.0, 4.5, 6.0, 1.0)
	var grape: float = VisualsRef._calc_senescence(4, 4.5, 1.0, 2.0, 4.5, 4.0, 0.0)
	assert_gt(maize, 0.5)
	assert_almost_eq(grape, 0.0, 0.001)


func test_derive_visual_state_keys_and_ranges() -> void:
	var tile := {
		"crop_key": "maize",
		"crop_stage": 4,
		"lai": 3.5,
		"grain_g_m2": 400.0,
		"dev_stage": 1.5,
		"lai_peak": 4.5,
	}
	var vis: Dictionary = VisualsRef.derive_visual_state(tile)
	for key: String in ["growth", "senescence", "repro", "yield_frac"]:
		assert_true(vis.has(key), "has %s" % key)
		assert_between(vis[key], 0.0, 1.0, key)
	assert_almost_eq(vis["yield_frac"], 0.5, 0.001, "400 of 800 g/m2 reference")
	assert_gt(vis["repro"], 0.0)
	assert_gt(vis["senescence"], 0.0, "Canopy below its peak has begun senescing")


func test_derive_visual_state_without_dev_stage_uses_nominal() -> void:
	var tile := {"crop_key": "spring_wheat", "crop_stage": 3, "lai": 4.0, "grain_g_m2": 0.0}
	var vis: Dictionary = VisualsRef.derive_visual_state(tile)
	assert_gt(vis["repro"], 0.0, "Flowering implies heading even without DVS")
	assert_eq(VisualsRef.derive_visual_state({"crop_stage": 0})["growth"], 0.0)


func test_grape_reference_yield_is_always_full() -> void:
	# Grape has no grain reference: cluster size never depends on grain mass.
	var vis: Dictionary = VisualsRef.derive_visual_state(
		{"crop_key": "grape", "crop_stage": 4, "lai": 3.0, "grain_g_m2": 0.0}
	)
	assert_almost_eq(vis["yield_frac"], 1.0, 0.001)
