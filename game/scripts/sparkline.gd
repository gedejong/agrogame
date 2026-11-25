extends Control
## Reusable sparkline graph — draws a polyline with auto-scaled Y axis.
## Supports stage markers as vertical dotted lines.

## A Quick Status gauge series (#669) plots on the card's fixed 0-100 scale.
const GAUGE_MIN := 0.0
const GAUGE_MAX := 100.0

var _data: PackedFloat64Array = PackedFloat64Array()
var _color := Color.WHITE
var _fill_color := Color(1, 1, 1, 0.1)
var _label := ""
var _unit := ""
var _stage_days: PackedInt32Array = PackedInt32Array()
var _stage_color := Color(1.0, 1.0, 1.0, 0.15)
var _y_min := 0.0
var _y_max := 1.0
var _gauge := false
var _value_shown := true


## `gauge`: a Quick Status gauge series, printed as the card's integer on a
## fixed 0-100 range (#669).
func setup(
	label: String,
	unit: String,
	color: Color,
	min_height: float = 40.0,
	gauge: bool = false,
) -> void:
	_label = label
	_unit = unit
	_color = color
	_fill_color = Color(color.r, color.g, color.b, 0.08)
	custom_minimum_size = Vector2(200, min_height)
	_gauge = gauge


## `value_shown` false prints "—" for the latest value, as the card does for a
## gauge that does not apply; the line still plots every day.
func set_data(
	data: PackedFloat64Array,
	stage_days: PackedInt32Array = PackedInt32Array(),
	value_shown: bool = true,
) -> void:
	_data = data
	_stage_days = stage_days
	_value_shown = value_shown
	_compute_range()
	queue_redraw()


func get_latest_value() -> float:
	if _data.is_empty():
		return 0.0
	return _data[_data.size() - 1]


## "<label>: <latest value>", as drawn above the line.
func label_text() -> String:
	if not _value_shown:
		return "%s: —" % _label
	if _data.is_empty():
		return "%s: " % _label
	return "%s: %s" % [_label, value_text(_data[_data.size() - 1], _unit, _gauge)]


## The latest value as printed: `integer` floors it as QuickStatusCard prints a
## gauge, else 0, 1 or 2 decimals by magnitude; then the unit.
static func value_text(latest: float, unit: String, integer: bool) -> String:
	var text := ""
	if integer:
		text = "%d" % floori(latest + 1e-6)
	elif absf(latest) >= 100.0:
		text = "%.0f" % latest
	elif absf(latest) >= 1.0:
		text = "%.1f" % latest
	else:
		text = "%.2f" % latest
	if not unit.is_empty():
		text += " " + unit
	return text


func _compute_range() -> void:
	if _gauge:
		_y_min = GAUGE_MIN
		_y_max = GAUGE_MAX
		return
	if _data.is_empty():
		_y_min = 0.0
		_y_max = 1.0
		return
	_y_min = _data[0]
	_y_max = _data[0]
	for v: float in _data:
		if v < _y_min:
			_y_min = v
		if v > _y_max:
			_y_max = v
	# Ensure range is never zero
	if _y_max - _y_min < 0.001:
		_y_max = _y_min + 1.0
	# Pad slightly
	var pad: float = (_y_max - _y_min) * 0.1
	_y_min -= pad
	_y_max += pad


func _draw() -> void:
	var w: float = size.x
	var h: float = size.y
	var label_h := 14.0
	var graph_y := label_h
	var graph_h: float = h - label_h - 2
	# Background
	draw_rect(Rect2(0, graph_y, w, graph_h), Color(1.0, 1.0, 1.0, 0.03))
	# Label + current value
	draw_string(
		ThemeDB.fallback_font,
		Vector2(2, label_h - 2),
		label_text(),
		HORIZONTAL_ALIGNMENT_LEFT,
		-1,
		10,
		_color
	)
	if _data.size() < 2:
		return
	var n: int = _data.size()
	var range_y: float = _y_max - _y_min
	# Stage markers (vertical lines)
	for sd: int in _stage_days:
		if sd >= 0 and sd < n:
			var sx: float = float(sd) / float(n - 1) * w
			for dy in range(0, int(graph_h), 4):
				draw_line(
					Vector2(sx, graph_y + dy),
					Vector2(sx, graph_y + minf(dy + 2, graph_h)),
					_stage_color,
					1.0
				)
	# Fill area under curve
	var fill_pts := PackedVector2Array()
	fill_pts.append(Vector2(0, graph_y + graph_h))
	for i in range(n):
		var x: float = float(i) / float(n - 1) * w
		var y: float = graph_y + graph_h - ((_data[i] - _y_min) / range_y) * graph_h
		fill_pts.append(Vector2(x, y))
	fill_pts.append(Vector2(w, graph_y + graph_h))
	draw_colored_polygon(fill_pts, _fill_color)
	# Polyline
	var pts := PackedVector2Array()
	for i in range(n):
		var x: float = float(i) / float(n - 1) * w
		var y: float = graph_y + graph_h - ((_data[i] - _y_min) / range_y) * graph_h
		pts.append(Vector2(x, y))
	draw_polyline(pts, _color, 1.5, true)
