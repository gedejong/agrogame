# ADR-005: Frontend Architecture

## Status: Proposed

## Context

The existing Streamlit dashboard (`agrogame.dashboard`) serves its purpose for diagnostic visualization during model development — Plotly charts of soil moisture profiles, nitrogen cycling, phenology curves. But Streamlit is a data app framework, not a game engine. It cannot support the interactive turn-based gameplay described in ADR-004: there is no persistent client state, no sprite/tile rendering, no WebSocket push for pause events, and the rerun-on-interaction model makes responsive UX impossible.

We need a frontend that supports: (1) a field overview with visual representation of crop state, (2) management plan editing UI, (3) fast-forward visualization of season progression, (4) responsive pause-event interrupts, and (5) end-of-season result dashboards. The simulation engine must remain in Python — it is 15k+ lines of validated agronomic models and rewriting it would be reckless.

## Decision

**Web application with React + TypeScript frontend and FastAPI backend. Separate repositories.**

### Backend (this repo: `agrogame`)

- A new `agrogame.api` package exposes the game engine via FastAPI.
- Key endpoints:
  - `POST /games` — create a new game (returns game ID, initial state).
  - `POST /games/{id}/plan` — submit a `ManagementPlan` for the current season.
  - `POST /games/{id}/advance` — run the season forward. Returns either a `PauseEvent` (with current state snapshot) or end-of-season results.
  - `POST /games/{id}/revise` — submit mid-season plan revision (only valid during a pause).
  - `GET /games/{id}/state` — current game state for reconnection.
- Game state is server-side. The frontend is stateless beyond UI concerns. This prevents cheating and simplifies the client.
- REST over HTTP, not WebSockets. The turn-based nature means request-response is sufficient. Season execution completes in < 1s (ADR-006), so long-polling or streaming is unnecessary.
- Response payloads include structured JSON for game state plus pre-rendered Plotly chart specs (as JSON) for data-heavy views. The frontend renders these via `plotly.js` without needing to understand agronomic data structures.

### Frontend (separate repo: `agrogame-web`)

- React 18+ with TypeScript. Vite for build tooling.
- Two visual modes:
  - **Field overview:** tile/sprite grid showing fields, crop growth stages (color-coded), irrigation status. Simple 2D — not pixel art, not 3D. CSS Grid or Canvas, decided during implementation.
  - **Data views:** Plotly.js charts for soil moisture, nutrient levels, yield projections. Reuses the chart specifications the Python backend already generates.
- Target platform: desktop web browsers (Chrome, Firefox, Safari). Mobile is a stretch goal — the management plan editing UI is inherently mouse-friendly.
- No client-side simulation logic. The frontend is a view layer that sends player decisions and renders server responses.

### Existing Streamlit dashboard

- Retained as-is for developer diagnostics and model validation. Not part of the game frontend. Lives in `agrogame.dashboard`, imports remain optional.

## Consequences

**Positive:**
- Clean separation: Python owns simulation truth, TypeScript owns presentation. Each can evolve independently.
- FastAPI is already in the Python ecosystem, integrates naturally with Pydantic models we already use for config/params.
- React + TypeScript is the largest frontend talent pool. Easy to find contributors or hand off.
- Plotly chart reuse means we do not rebuild 20+ diagnostic visualizations — they transfer directly.
- REST API enables future clients (mobile app, CLI tool, automated tournament runner) without backend changes.
- Server-side state prevents client-side cheating and makes multiplayer a future possibility.

**Negative:**
- Two repositories means two CI pipelines, two deploy targets, cross-repo version coordination.
- FastAPI adds a dependency and a new package (`agrogame.api`) to maintain. API versioning must be planned early.
- REST request-response means the frontend cannot show real-time day-by-day animation during fast-forward. The season result arrives as a batch. If we later want animated playback, we would need to return a time-series of snapshots (acceptable overhead given ADR-006 performance targets).
- React + TypeScript is a hard dependency on the JavaScript ecosystem. Contributors must be comfortable in both Python and TypeScript.

## Alternatives Considered

**Streamlit as game frontend.** Rejected. Streamlit reruns the entire script on each interaction, cannot maintain WebSocket connections, has no sprite/tile rendering, and provides no control over layout below the widget level. It is the right tool for data dashboards, not games.

**Godot / Unity with Python bindings.** Rejected. Massive dependency for a 2D turn-based farm game. Godot's GDScript or Unity's C# would require rewriting or wrapping the entire simulation engine. Build tooling, packaging, and distribution become dramatically more complex. The visual fidelity these engines provide is unnecessary — we are not building Stardew Valley.

**Python-native GUI (Tkinter, PyQt, Kivy).** Rejected. Limited to desktop. Packaging and distribution are painful (PyInstaller, cx_Freeze). UI toolkit quality and ecosystem are far behind web. Multiplayer becomes very difficult.

**Embedded Python in browser (Pyodide/PyScript).** Rejected. The simulation engine uses numpy, scipy, and potentially Rust extensions (ADR-006). Pyodide support for these is incomplete and performance in WASM is 3-10x slower than native. Server-side execution is simpler and faster.

**Single repo (monorepo) for frontend and backend.** Considered but deferred. A monorepo adds complexity to CI (must detect which part changed), mixes Python and Node tooling, and creates confusing directory structures. If coordination pain becomes real, we can consolidate later. Starting with separate repos is easier to reason about.
