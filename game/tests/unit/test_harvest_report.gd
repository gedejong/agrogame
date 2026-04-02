extends GutTest
## Tests for harvest report screen constants and grade colors.

const HarvestReport = preload("res://scripts/harvest_report.gd")


func test_grade_colors_defined() -> void:
	assert_true(HarvestReport.GRADE_COLORS.has("A"), "Grade A color defined")
	assert_true(HarvestReport.GRADE_COLORS.has("B"), "Grade B color defined")
	assert_true(HarvestReport.GRADE_COLORS.has("C"), "Grade C color defined")
	assert_true(HarvestReport.GRADE_COLORS.has("D"), "Grade D color defined")
	assert_true(HarvestReport.GRADE_COLORS.has("F"), "Grade F color defined")


func test_grade_a_is_greenish() -> void:
	var color: Color = HarvestReport.GRADE_COLORS["A"]
	assert_true(color.g > color.r, "Grade A should be green-dominant")


func test_grade_f_is_reddish() -> void:
	var color: Color = HarvestReport.GRADE_COLORS["F"]
	assert_true(color.r > color.g, "Grade F should be red-dominant")


func test_grade_colors_count() -> void:
	assert_eq(HarvestReport.GRADE_COLORS.size(), 5, "Should have 5 grades A-F")
