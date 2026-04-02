extends RefCounted
## Maize-specific procedural crop rendering.
## Draws corn leaves as Line2D arcs with per-leaf variation,
## canopy shadow, senescence yellowing, and narrow-wide-narrow shape.

const CropRenderer = preload("res://scripts/crop_renderer.gd")


static func draw_leaves(
	leaf_node: Node2D,
	senescence: float,
	stress: int,
	stem_height_frac: float,
	growth_progress: float,
	plant_seed: int = 0,
) -> void:
	for child in leaf_node.get_children():
		child.queue_free()

	var max_leaves := 10
	var num_leaves: int = int(clampf(growth_progress, 0.0, 1.0) * max_leaves)
	if num_leaves < 1:
		return

	var stem_px: float = 32.0 * CropRenderer._PLANT_SCALE.y * stem_height_frac
	var sf: float = CropRenderer._PLANT_SCALE.x

	for li in range(num_leaves):
		var frac: float = float(li) / float(max_leaves)
		var h := ((li + plant_seed * 31) * 2654435761) & 0x7FFFFFFF
		var rh := func(idx: int) -> float: return CropRenderer.root_hash(h, idx)

		var y_frac: float = 0.03 + frac * 0.82
		var y: float = -y_frac * stem_px
		var dir: float = -1.0 if li % 2 == 0 else 1.0
		var age: float = 1.0 - frac

		# Bell-curve leaf length
		var len_curve: float = 1.0 - 4.0 * (frac - 0.55) * (frac - 0.55)
		var len_var: float = (rh.call(0) - 0.5) * 0.3
		var base_len: float = (5.0 + len_curve * 5.0) * sf * (1.0 + len_var)

		# Lower leaves droop, upper point up
		var droop_var: float = (rh.call(1) - 0.5) * 0.2
		var droop_strength: float = (0.2 + 1.6 * age * age) * sf * (1.0 + droop_var)

		# Camera facing
		var facing: float = rh.call(2)
		var width_mult: float = 0.6 + facing * 0.4

		var curve_var: float = (rh.call(3) - 0.5) * 0.2

		# Arc shape: up then tip droop
		var pts := PackedVector2Array()
		var segs := 7
		var eff_len: float = base_len * (0.7 + facing * 0.3)
		var rise_height: float = eff_len * (0.5 + curve_var * 0.15)
		for si in range(segs + 1):
			var t: float = float(si) / float(segs)
			var x: float = dir * eff_len * t
			var arc_up: float = -rise_height * 4.0 * t * (1.0 - t)
			var tip_droop: float = droop_strength * t * t * t
			pts.append(Vector2(x, y + arc_up + tip_droop))

		# Colors — mostly dark, rare bright highlights
		var leaf_sen: float = clampf(senescence - (1.0 - frac) * 0.3, 0.0, 1.0)
		var hue_shift: float = (rh.call(5) - 0.5) * 0.03
		var base_green := Color(0.18 + hue_shift, 0.38 + hue_shift, 0.12)
		base_green = base_green.darkened(age * 0.18)
		# Only very high-facing leaves catch light (facing³ = rare bright)
		base_green = base_green.lightened(facing * facing * facing * 0.4)
		var senescent_color := Color(0.65, 0.58, 0.28)
		var dead_color := Color(0.5, 0.4, 0.22)
		var color := base_green.lerp(senescent_color, leaf_sen * 0.85)
		color = color.lerp(dead_color, maxf(leaf_sen - 0.5, 0.0) * 1.6)
		if stress == CropRenderer.STRESS_WILTING:
			color = color.lerp(Color(0.42, 0.35, 0.16), 0.45)
		elif stress == CropRenderer.STRESS_N_DEFICIENT:
			color = color.lerp(Color(0.58, 0.6, 0.25), 0.35)

		var tip_color := color.lightened(0.12)
		tip_color.a = 0.8

		var base_w: float = (1.8 - frac * 0.3) * sf * width_mult
		var w_curve := Curve.new()
		w_curve.add_point(Vector2(0.0, 0.3))
		w_curve.add_point(Vector2(0.15, 0.8))
		w_curve.add_point(Vector2(0.35, 1.0))
		w_curve.add_point(Vector2(0.65, 0.7))
		w_curve.add_point(Vector2(1.0, 0.05))

		# Main leaf
		var leaf := Line2D.new()
		leaf.points = pts
		leaf.width_curve = w_curve
		leaf.width = base_w
		var grad := Gradient.new()
		grad.set_color(0, color)
		grad.set_color(1, tip_color)
		leaf.gradient = grad
		leaf_node.add_child(leaf)

	# Soft blurred shadow — proportional to plant size
	if num_leaves > 3:
		var plant_spread: float = growth_progress * sf * 8.0
		var shadow_w: float = plant_spread * 0.8
		var shadow_h: float = plant_spread * 0.25
		var blur_steps := 1
		for bi in range(blur_steps, -1, -1):
			var expand: float = float(bi) * 1.2
			var alpha: float = 0.06 if bi > 0 else 0.15
			var shadow := Polygon2D.new()
			var shadow_pts := PackedVector2Array()
			for si in range(12):
				var angle: float = float(si) * TAU / 12.0
				(
					shadow_pts
					. append(
						Vector2(
							cos(angle) * (shadow_w * 0.5 + expand) - 1.5,
							sin(angle) * (shadow_h * 0.5 + expand * 0.3) + 3.0,
						)
					)
				)
			shadow.polygon = shadow_pts
			shadow.color = Color(0.0, 0.04, 0.0, alpha)
			leaf_node.add_child(shadow)
			leaf_node.move_child(shadow, 0)
