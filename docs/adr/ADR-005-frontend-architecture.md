# ADR-005: Frontend Architecture

## Status: Accepted

**Update (AGRO-113):** Monorepo structure — Godot project lives in `game/`
alongside the Python simulation. GDScript is the primary scripting language
(Python-like, accessible to the team). C# available for performance-critical
rendering paths via Godot's C# support. Path-filtered CI ensures Python and
Godot jobs run independently.

## Context

The simulation engine is mature: validated, calibrated, multi-season, 7 crops,
3 climates, irrigation, fertilization, crop rotation, 3-pool SOM with aggregate
protection. But a data dashboard is not a game. The existing Streamlit dashboard
serves model validation — Plotly charts, diagnostic panels. It cannot make a
player *feel* like a farmer.

We need a frontend that does three things:

1. **Makes farming tangible.** You look at your fields and see crops growing,
   rain sweeping across, leaves yellowing under nitrogen stress. You don't read
   "N stress = 0.6" — you see the lower leaves turning pale and think "I should
   have fertilized last week."

2. **Shows what's happening underground.** This is the game's differentiator.
   Click any patch and the camera slides down into a 3D cross-section of the
   soil profile. You see water percolating through layers after rain, roots
   growing deeper each week, nitrogen leaching past the root zone, microbial
   activity pulsing near root tips. Every concept from a soil science textbook
   becomes a living animation. *This is how players learn.*

3. **Supports the turn-based loop.** Season planning, fast-forward through
   growth, pause at events, harvest and review. The engine stays in Python —
   15k+ lines of validated agronomic models that we are not rewriting.

## Decision

**Godot 4 game client with FastAPI REST backend. Separate repositories.**

### Why Godot 4

The underground soil visualization requires mixed 2D and 3D rendering in the
same scene — an isometric field overview *and* a 3D soil cross-section with
particle effects, shaders, and animated root growth. This rules out pure 2D
web renderers (PixiJS, Phaser) and makes a game engine the right tool.

Godot 4 is the engine because:

- **Native 2D + 3D mixing.** Isometric field view (2D) and soil cross-section
  (3D) coexist in the same scene tree. No awkward multi-renderer plumbing.
- **GPU particle systems.** Water percolation, microbial activity, fertilizer
  dissolution — all need thousands of small, physics-influenced particles.
  Godot's GPUParticles3D handles this natively.
- **Shader support.** Nutrient gradient overlays (N green fading with depth,
  P purple at the surface), moisture saturation effects, SOM pool density
  visualization — all done with spatial shaders on the soil cross-section mesh.
- **GDScript is Python-like.** The team already thinks in Python. GDScript's
  syntax, duck typing, and indentation-based scoping make it immediately
  productive. C# is available for performance-critical paths.
- **MIT license.** Free forever. No revenue royalties, no licensing surprises.
- **Web export via WASM.** Desktop-first, but web is a realistic stretch goal.
- **~40MB engine.** Lightweight CI, fast iteration.

### The Game World

#### The Farm (main view — isometric 2D)

The player sees their farm from a warm, angled overhead perspective. Fields are
laid out on gently rolling terrain. Each field is divided into patches —
visually distinct by soil type (sandy patches are pale beige, clay patches are
dark ochre, organic-rich patches are deep chocolate brown).

Crops are visible as growth stages: bare tilled soil → tiny seedlings pushing
through → full green canopy → golden grain heads nodding in the breeze →
stubble after harvest. You watch the season unfold.

Stress shows before the numbers do:
- **Drought:** leaves curl inward, canopy thins, soil lightens and cracks
- **Nitrogen deficiency:** lower leaves yellow (chlorosis), working upward
- **Waterlogging:** standing water shimmers on the surface, leaves droop
- **Heat stress:** leaves pale, growth stalls visibly

Weather moves across the scene: rain sweeps field by field, frost crystals form
overnight, heat shimmer rises on hot days. Seasons shift the entire palette —
spring green, summer lush, autumn gold, winter dormant grey.

#### The Underground (soil cross-section — 3D)

Click any patch and the camera tilts and slides into the ground. A 3D cutaway
opens, showing the actual soil profile from the simulation:

- **Layers** rendered with distinct textures matching their properties: sandy
  topsoil (grainy, light), clay subsoil (smooth, dense), organic horizon
  (dark, crumbly). Layer boundaries match `SoilProfile.layers` exactly.
- **Water** percolates visually — blue particle streams trickling through pore
  spaces after rain, pooling above clay layers, draining slowly through the
  profile. The speed matches the cascading bucket model output.
- **Roots** grow downward over the season — white tendrils branching and
  deepening, following the `RootState.current_depth_cm` trajectory. Root
  density fades with depth matching the exponential distribution.
- **Nutrients** glow as color overlays on the soil mesh: nitrogen (green) fading
  with depth as leaching removes it, phosphorus (purple) concentrated near the
  surface where it's fixed.
- **SOM pools** are visible as organic matter clusters — labile near the surface
  (actively decomposing, small particles breaking apart), stable pool deeper
  (large dark aggregates, barely changing). Aggregate protection is visible as
  clay-encased organic particles.
- **Microbes** appear as tiny luminous bursts near active root tips —
  rhizosphere priming made visible. Activity correlates with the
  `MicrobialActivityComputed` events from the simulation.
- **Fertilizer application** shows granules dissolving at the surface, nitrogen
  spreading into the top layer, then slowly leaching deeper.

This view is *the reason the game exists.* It turns every concept from a soil
science textbook into a living, breathing animation that a player discovers by
playing, not by reading.

#### Planning Screen

Seasonal calendar with drag-and-drop management events. Each action shows its
cost (ADR-003). Weather forecast with uncertainty bands. ManagementPlan
visualization per patch.

#### Harvest Report

Split view: your yield vs GYGA potential for that climate. Soil health
trajectory (SOM change over years). Economic P&L with letter grade. Crop
rotation history timeline.

### Art Style

Not pixel art (too retro for an educational tool). Not photorealistic (too
expensive, too sterile). Clean, modern, slightly stylized — think *Monument
Valley meets agricultural textbook.* Warm earth-tone palette, soft directional
lighting, gentle shadows. Infographic-quality data visualization layered
naturally into the game world. The aesthetic says: "this is serious science
presented with care and beauty."

### Backend (this repo: `agrogame`)

- New `agrogame.api` package exposes the game engine via FastAPI.
- Key endpoints:
  - `POST /games` — create game (returns ID, initial state)
  - `POST /games/{id}/plan` — submit ManagementPlan for current season
  - `POST /games/{id}/advance` — run season, return PauseEvent or results
  - `POST /games/{id}/revise` — mid-season plan revision (during pause)
  - `GET /games/{id}/state` — current state for reconnection
- Game state is server-side. Godot client is a view layer.
- REST over HTTP. Turn-based = request-response is sufficient.
- Response payloads include structured JSON for game state plus time-series
  snapshots for animated playback in the client.

### Frontend (separate repo: `agrogame-godot`)

- Godot 4.3+ with GDScript (C# for performance-critical rendering).
- Isometric field view (2D TileMap) + 3D soil cross-section (SubViewport).
- Desktop-first (Windows, macOS, Linux). Web export (WASM) as stretch goal.
- Communicates with FastAPI backend via HTTPClient (built-in Godot class).

### Existing Streamlit dashboard

Retained as-is for developer diagnostics and model validation only. Not part
of the game. Lives in `agrogame.dashboard`, imports remain optional.

## Consequences

**Positive:**
- The underground view creates a genuinely novel educational experience —
  no other farming game shows live soil biogeochemistry.
- Godot's mixed 2D/3D handles both the field overview and soil cutaway without
  renderer hacks.
- GDScript's Python-like syntax keeps the team productive from day one.
- MIT license and small engine footprint keep CI fast and licensing clean.
- FastAPI integration reuses Pydantic models we already have.
- Server-side state prevents cheating and enables future multiplayer.
- Desktop-first means no WebGL limitations for the 3D soil view.

**Negative:**
- Two repositories (Python simulation + Godot client) with cross-repo
  coordination and separate CI pipelines.
- GDScript is Python-*like* but not Python. Team needs to learn Godot's scene
  tree, signal system, and node lifecycle.
- Art asset creation is a new workstream: crop sprites (7 crops x 6 growth
  stages), soil textures, particle effects, weather overlays, UI elements.
  Requires either a dedicated artist or adaptation of open-source assets.
- Godot's web export (WASM) works but produces large bundles (~30-50MB) and
  has threading limitations. Desktop is the primary target.
- Fewer contributors know GDScript/Godot than React/TypeScript. Smaller
  hiring pool for the frontend.

## Alternatives Considered

**React + PixiJS (2D WebGL).** Was the original recommendation. Rejected
because PixiJS cannot render the 3D soil cross-section — the underground view
needs real 3D geometry, particles, and spatial shaders. A pure 2D renderer
would force us to fake the most important visual in the game.

**React + Three.js (3D in browser).** Could handle the soil view, but managing
a Three.js scene alongside React state is complex. No built-in game engine
features (scene tree, input handling, animation player). Would require
building engine-level infrastructure from scratch.

**Unity.** Technically capable but: proprietary license with changing terms
(Runtime Fee controversy), C# is a bigger language jump than GDScript, 1GB+
engine, and the project philosophy favors open-source tools.

**Unreal Engine.** Massively overkill. 50GB+ install, C++ codebase, designed
for AAA 3D — not a turn-based farm game with 2D/3D hybrid needs. 5% revenue
royalty above $1M.

**Streamlit as game frontend.** Rejected. Reruns on every interaction, no
persistent state, no sprite or 3D rendering, no control over layout. Right
tool for data apps, wrong tool for games.

**Godot with embedded WebView for charts.** Considered for Plotly chart reuse.
Deferred — Godot's native UI (Label, HBoxContainer, custom drawing) is
sufficient for in-game dashboards. Detailed analytics stay in Streamlit for
developers.
