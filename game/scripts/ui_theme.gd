class_name UiTheme
extends RefCounted
## Shared UI theme: glassmorphism design system per art guide.
## Dark slate-navy with transparency — Cities: Skylines II / Frostpunk.

# --- Panel backgrounds ---
## Primary panel: #1E2532 at 80% opacity
const PANEL_BG := Color(0.118, 0.145, 0.196, 0.80)
## Inner card: white at 6%
const INNER_CARD_BG := Color(1.0, 1.0, 1.0, 0.06)
## Inline element: white at 4%
const INLINE_BG := Color(1.0, 1.0, 1.0, 0.04)
## Bottom HUD bar: #161C24 at 85%
const BAR_BG := Color(0.086, 0.110, 0.141, 0.85)

# --- Borders & shadows ---
const BORDER_COLOR := Color(1.0, 1.0, 1.0, 0.12)
const SHADOW_COLOR := Color(0, 0, 0, 0.3)
const SHADOW_SIZE := 6
const DIVIDER_COLOR := Color(1.0, 1.0, 1.0, 0.12)

# --- Corner radii ---
const CORNER_RADIUS := 10
const INNER_RADIUS := 8
const PILL_RADIUS := 4

# --- Typography ---
const TEXT_PRIMARY := Color.WHITE
const TEXT_SECONDARY := Color(0.627, 0.667, 0.710)  # #A0AAB5
const TEXT_MUTED := Color(0.627, 0.667, 0.710, 0.7)
const TEXT_DISABLED := Color(1.0, 1.0, 1.0, 0.3)

# --- Button states ---
const BTN_NORMAL_BG := Color(1.0, 1.0, 1.0, 0.08)
const BTN_HOVER_BG := Color(1.0, 1.0, 1.0, 0.14)
const BTN_PRESSED_BG := Color(1.0, 1.0, 1.0, 0.05)
const BTN_DISABLED_BG := Color(1.0, 1.0, 1.0, 0.03)
const BTN_BORDER := Color(1.0, 1.0, 1.0, 0.10)
const BTN_HOVER_BORDER := Color(1.0, 1.0, 1.0, 0.25)
const BTN_CORNER_RADIUS := 6

# --- Functional accent colors ---
const ACCENT_GREEN := Color(0.290, 0.871, 0.502)  # #4ADE80
const ACCENT_RED := Color(0.937, 0.267, 0.267)  # #EF4444
const ACCENT_GOLD := Color(0.984, 0.749, 0.141)  # #FBBF24
const ACCENT_BLUE := Color(0.376, 0.647, 0.980)  # #60A5FA
const ACCENT_LIME := Color(0.502, 0.800, 0.333)  # #80CC55 — N-available

# --- Icon tint ---
const ICON_TINT := Color.WHITE
const ICON_MUTED := Color(0.627, 0.667, 0.710)

# --- Graph / sparkline ---
const GRAPH_BG := Color(1.0, 1.0, 1.0, 0.04)
const STAGE_MARKER := Color(1.0, 1.0, 1.0, 0.15)

# --- Progress bar ---
const TRACK_BG := Color(1.0, 1.0, 1.0, 0.05)
const OPT_ZONE := Color(1.0, 1.0, 1.0, 0.06)

# --- Blur shader ---
const BLUR_SHADER_PATH := "res://shaders/ui_blur.gdshader"
const BLUR_AMOUNT := 3.0

# --- Legacy aliases for panels that still reference old names ---
const HEADER_COLOR := TEXT_PRIMARY
const BODY_COLOR := TEXT_PRIMARY
const MUTED_COLOR := TEXT_SECONDARY
const VALUE_COLOR := TEXT_PRIMARY
const SEPARATOR_COLOR := DIVIDER_COLOR


static func create_panel_style(transparent: bool = false) -> StyleBoxFlat:
	"""Primary panel: dark slate-navy glass, rounded, bordered, shadowed."""
	var s := StyleBoxFlat.new()
	s.bg_color = Color(0, 0, 0, 0) if transparent else PANEL_BG
	s.corner_radius_top_left = CORNER_RADIUS
	s.corner_radius_top_right = CORNER_RADIUS
	s.corner_radius_bottom_left = CORNER_RADIUS
	s.corner_radius_bottom_right = CORNER_RADIUS
	s.content_margin_left = 16
	s.content_margin_right = 16
	s.content_margin_top = 16
	s.content_margin_bottom = 16
	s.border_width_left = 1
	s.border_width_right = 1
	s.border_width_top = 1
	s.border_width_bottom = 1
	s.border_color = BORDER_COLOR
	s.shadow_color = SHADOW_COLOR
	s.shadow_size = SHADOW_SIZE
	s.shadow_offset = Vector2(0, 2)
	return s


static func create_bar_style(transparent: bool = false) -> StyleBoxFlat:
	"""Bottom HUD bar style (top bar / action bar strips)."""
	var s := create_panel_style(transparent)
	if not transparent:
		s.bg_color = BAR_BG
	s.corner_radius_top_left = 0
	s.corner_radius_top_right = 0
	s.shadow_size = 2
	return s


static func create_hud_style(transparent: bool = false) -> StyleBoxFlat:
	"""Bottom HUD bar: full-width, no bottom corners, generous padding."""
	var s := create_bar_style(transparent)
	s.corner_radius_bottom_left = 0
	s.corner_radius_bottom_right = 0
	s.content_margin_left = 12
	s.content_margin_right = 12
	s.content_margin_top = 6
	s.content_margin_bottom = 6
	return s


static func add_divider(parent: Node, at_index: int) -> void:
	"""Insert a styled HSeparator into parent at the given child index."""
	var div := HSeparator.new()
	var s := StyleBoxFlat.new()
	s.bg_color = DIVIDER_COLOR
	s.content_margin_top = 2
	s.content_margin_bottom = 2
	div.add_theme_stylebox_override("separator", s)
	parent.add_child(div)
	parent.move_child(div, at_index)


static func create_inner_card_style() -> StyleBoxFlat:
	"""Inner card: subtle white overlay inside a panel."""
	var s := StyleBoxFlat.new()
	s.bg_color = INNER_CARD_BG
	s.corner_radius_top_left = INNER_RADIUS
	s.corner_radius_top_right = INNER_RADIUS
	s.corner_radius_bottom_left = INNER_RADIUS
	s.corner_radius_bottom_right = INNER_RADIUS
	s.content_margin_left = 12
	s.content_margin_right = 12
	s.content_margin_top = 12
	s.content_margin_bottom = 12
	return s


static func create_button_style(state: String) -> StyleBoxFlat:
	"""Button StyleBoxFlat for normal/hover/pressed/disabled."""
	var s := StyleBoxFlat.new()
	s.corner_radius_top_left = BTN_CORNER_RADIUS
	s.corner_radius_top_right = BTN_CORNER_RADIUS
	s.corner_radius_bottom_left = BTN_CORNER_RADIUS
	s.corner_radius_bottom_right = BTN_CORNER_RADIUS
	s.content_margin_left = 8
	s.content_margin_right = 8
	s.content_margin_top = 6
	s.content_margin_bottom = 6
	s.border_width_left = 1
	s.border_width_right = 1
	s.border_width_top = 1
	s.border_width_bottom = 1
	match state:
		"hover":
			s.bg_color = BTN_HOVER_BG
			s.border_color = BTN_HOVER_BORDER
		"pressed":
			s.bg_color = BTN_PRESSED_BG
			s.border_color = BTN_BORDER
		"disabled":
			s.bg_color = BTN_DISABLED_BG
			s.border_color = Color(0, 0, 0, 0)
		_:
			s.bg_color = BTN_NORMAL_BG
			s.border_color = BTN_BORDER
	return s


static func style_button(btn: Button) -> void:
	"""Apply full glassmorphism theme to a Button (all 4 states + text)."""
	btn.add_theme_stylebox_override("normal", create_button_style("normal"))
	btn.add_theme_stylebox_override("hover", create_button_style("hover"))
	btn.add_theme_stylebox_override("pressed", create_button_style("pressed"))
	btn.add_theme_stylebox_override("disabled", create_button_style("disabled"))
	btn.add_theme_color_override("font_color", TEXT_SECONDARY)
	btn.add_theme_color_override("font_hover_color", TEXT_PRIMARY)
	btn.add_theme_color_override("font_pressed_color", TEXT_PRIMARY)
	btn.add_theme_color_override("font_disabled_color", TEXT_DISABLED)
	btn.add_theme_color_override("icon_normal_color", TEXT_SECONDARY)
	btn.add_theme_color_override("icon_hover_color", TEXT_PRIMARY)


static func wrap_in_panel(node: Control, style: StyleBoxFlat) -> PanelContainer:
	"""Reparent a Control inside a styled PanelContainer at the same tree position."""
	var parent: Node = node.get_parent()
	var idx: int = node.get_index()
	var rect := Rect2(node.offset_left, node.offset_top, node.offset_right, node.offset_bottom)
	parent.remove_child(node)
	var bg := PanelContainer.new()
	bg.add_theme_stylebox_override("panel", style)
	bg.add_child(node)
	parent.add_child(bg)
	parent.move_child(bg, idx)
	bg.offset_left = rect.position.x
	bg.offset_top = rect.position.y
	bg.offset_right = rect.size.x
	bg.offset_bottom = rect.size.y
	return bg


static func style_vseparator(sep: VSeparator) -> void:
	"""Apply muted divider style to a VSeparator."""
	var s := StyleBoxFlat.new()
	s.bg_color = DIVIDER_COLOR
	s.content_margin_left = 4
	s.content_margin_right = 4
	sep.add_theme_stylebox_override("separator", s)


static func replace_spacers(parent: Node, names: Array) -> void:
	"""Replace named spacer Controls with styled VSeparators."""
	for spacer_name: String in names:
		var spacer: Control = parent.get_node(spacer_name)
		var sep := VSeparator.new()
		style_vseparator(sep)
		var idx: int = spacer.get_index()
		parent.remove_child(spacer)
		spacer.queue_free()
		parent.add_child(sep)
		parent.move_child(sep, idx)


static func style_popup_menu(popup: PopupMenu) -> void:
	"""Apply dark glassmorphism theme to a PopupMenu."""
	var panel_style := create_panel_style()
	panel_style.content_margin_left = 4
	panel_style.content_margin_right = 4
	panel_style.content_margin_top = 4
	panel_style.content_margin_bottom = 4
	popup.add_theme_stylebox_override("panel", panel_style)
	var hover_style := StyleBoxFlat.new()
	hover_style.bg_color = BTN_HOVER_BG
	hover_style.corner_radius_top_left = 4
	hover_style.corner_radius_top_right = 4
	hover_style.corner_radius_bottom_left = 4
	hover_style.corner_radius_bottom_right = 4
	popup.add_theme_stylebox_override("hover", hover_style)
	popup.add_theme_color_override("font_color", TEXT_PRIMARY)
	popup.add_theme_color_override("font_hover_color", TEXT_PRIMARY)


static func add_blur_bg(panel: Control, tint: Color = PANEL_BG) -> ColorRect:
	"""Insert a blur ColorRect as first child of panel.

	The panel must use create_panel_style(true) so its bg is transparent
	and the blur shader provides the frosted glass visual.
	"""
	var shader: Shader = load(BLUR_SHADER_PATH)
	if not shader:
		return null
	var mat := ShaderMaterial.new()
	mat.shader = shader
	mat.set_shader_parameter("blur_amount", BLUR_AMOUNT)
	mat.set_shader_parameter("tint_color", tint)
	var rect := ColorRect.new()
	rect.material = mat
	rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	rect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rect.size_flags_vertical = Control.SIZE_EXPAND_FILL
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(rect)
	panel.move_child(rect, 0)
	return rect


static func style_label(label: Label, type: String) -> void:
	"""Set label font color and style by type: header, body, muted, value."""
	match type:
		"header":
			label.add_theme_color_override("font_color", TEXT_PRIMARY)
			label.uppercase = true
		"body":
			label.add_theme_color_override("font_color", TEXT_SECONDARY)
		"muted":
			label.add_theme_color_override("font_color", TEXT_MUTED)
		_:
			label.add_theme_color_override("font_color", TEXT_PRIMARY)
