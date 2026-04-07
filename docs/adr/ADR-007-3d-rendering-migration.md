# ADR-007: Migration from 2D Sprites to 3D Rendering with 2.5D Appearance

## Status
Proposed

## Context

The current frontend uses Godot's 2D systems (TileMapLayer, Sprite2D, Line2D, Polygon2D) to render an isometric farming game. While functional, this approach has hit scaling limits:

- **SVG sprites** don't scale well across zoom levels and require separate assets per crop × stage × stress
- **Procedural 2D leaves** (Line2D arcs) are complex, create many nodes (~160 per tile), and can't cast real shadows
- **Soil cutaway** fakes 3D depth with 2D polygon math, producing brittle geometry code (700 lines)
- **No real lighting** — all shading is manually computed per vertex/face
- **No depth buffer** — z-ordering via `z_index = row + col` breaks with complex overlapping geometry
- **Camera locked** — no rotation possible in 2D; zoom is resolution-dependent
- **Future features** (terrain elevation, buildings, water bodies, weather volumes) are impractical in 2D

The game's "Monument Valley meets agricultural textbook" aesthetic is itself 3D-rendered. Moving to 3D with orthographic projection achieves the same 2.5D look while unlocking real depth, lighting, and scalability.

## Decision

Migrate the game world rendering from 2D (Node2D, TileMapLayer, Sprite2D) to 3D (Node3D, MeshInstance3D, Camera3D) while maintaining the current 2.5D isometric appearance via orthographic projection.

### Key architectural choices:

1. **Camera**: Camera3D with orthographic projection, positioned at 45° azimuth / 30° elevation to match current isometric angle. Zoom via `size` property.

2. **Ground tiles**: Single procedural ArrayMesh (or MultiMeshInstance3D) with per-tile material data driven by shader uniforms. Soil type, SOM, and moisture modulate tile appearance via a single shader — no per-tile Sprite2D overlays.

3. **Crops**: Phase 1 uses billboard Sprite3D (reuse existing SVGs). Phase 2 replaces with procedural 3D geometry (leaves as tessellated quads, stems as cylinders) using MultiMeshInstance3D for performance.

4. **Soil cutaway**: Real 3D cross-section geometry with CSGBox3D or ArrayMesh. Water as animated transparent material. Roots as 3D tube meshes. Dramatically simpler code than current 2D polygon math.

5. **Lighting**: DirectionalLight3D at top-left 45° (matching art guide). WorldEnvironment for ambient light and sky. Real-time shadows on crops.

6. **Interaction**: PhysicsRayQueryParameters3D raycasting replaces tile_layer.local_to_map() for click detection. StaticBody3D collision shapes per tile.

7. **UI stays 2D**: All CanvasLayer UI (forecast panel, action bar, harvest report, status bar) remains unchanged. Only the game world moves to 3D.

8. **Weather**: CPUParticles2D → GPUParticles3D for rain. World-space particles that interact with lighting.

### What does NOT change:
- API client and data flow (rendering-agnostic)
- UI panels (CanvasLayer-based, already decoupled)
- Game logic (all in Python backend)
- Art guide color palette and HSV guardrails
- Asset file organization

## Migration Strategy

**Incremental, not big-bang.** Each phase produces a working game:

| Phase | Scope | Outcome |
|-------|-------|---------|
| 0 | 3D scaffold | Camera3D + lights + empty scene, side-by-side with 2D |
| 1 | Ground tiles | 3D tile grid replaces TileMapLayer, clickable |
| 2 | Crops | Billboard sprites in 3D world, growth stages work |
| 3 | Soil cutaway | Real 3D cross-section, water, roots |
| 4 | Effects | Rain particles, shadows, environment |
| 5 | Terrain | Surrounding landscape in 3D |
| 6 | Procedural crops | 3D leaf geometry replaces billboards |

## Consequences

### Positive
- Real depth sorting (no more z_index hacks)
- Real lighting and shadows (huge visual quality jump)
- Camera flexibility (zoom works naturally, optional slight rotation)
- Simpler geometry code (3D math is more intuitive than 2D isometric projection)
- GPU-accelerated rendering (MultiMesh, shaders)
- Natural extension to terrain elevation, buildings, water bodies
- Weather effects integrate naturally (volumetric rain, fog)

### Negative
- ~2 weeks of migration work across 6 phases
- Learning curve for 3D-specific Godot APIs (shaders, mesh construction)
- Some existing GUT tests will need rewriting (those testing 2D node types)
- SVG crop sprites become temporary (billboards) until procedural 3D replaces them
- Slightly higher GPU requirements (mitigated by orthographic + low-poly style)

### Risks
- Performance regression if mesh construction is naive (mitigate: MultiMesh, LOD, shader-based)
- Visual regression during transition (mitigate: keep 2D as fallback until 3D matches quality)
- Soil cutaway complexity in 3D (mitigate: use CSGBox3D for prototyping, optimize later)

## References
- Godot 4 3D tutorial: orthographic isometric camera setup
- Monument Valley GDC talk: orthographic 3D with fixed camera angle
- Current codebase: `game/scripts/farm_view.gd` (1067 lines), `soil_view.gd` (696 lines)
