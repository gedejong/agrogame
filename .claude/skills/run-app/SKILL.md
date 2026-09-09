---
name: run-app
description: "Launch and drive AgroGame locally: Poetry venv on Python 3.12, FastAPI backend on port 8000 (make serve-api), Godot 4 client (godot --path game), API smoke script, Movie Maker screenshot"
allowed-tools: ["Bash", "Read"]
---

# Run AgroGame locally

Two processes make up the running project: the FastAPI backend on
`localhost:8000` and the Godot 4 client, which talks to it over HTTP. Start
the backend first; the client creates a game against it on launch.

Verified on macOS (Apple Silicon) with Homebrew Godot 4.7.1. The Linux path
is the one CI uses (`.github/workflows/`): Python 3.10 via setup-python and
Godot via `chickensoft-games/setup-godot`.

## Prerequisites and setup

- Poetry >= 2.1 and a **Python 3.10 to 3.12** interpreter. The lock pins
  `numpy 1.26.4`, which has no wheels for 3.13 or 3.14; Homebrew's default
  `python3` is newer, so point Poetry at 3.12 explicitly.
- Godot 4.6+ on `PATH` as `godot` (CI pins 4.6.1; 4.7.1 opens the project
  without changes).

```bash
poetry env use python3.12
poetry install --no-interaction --with dev -E api   # api extra = fastapi + uvicorn
(cd game && godot --headless --import)              # asset import into game/.godot; first run or after asset changes
```

Godot writes a `.gd.uid` sidecar next to any script that lacks one. The repo
tracks these files, so new ones appear as untracked; commit or delete them.

## Run the backend

```bash
make serve-api &> /tmp/agrogame-api.log &
API_PID=$!
```

This runs `uvicorn ... --reload --port 8000` bound to `127.0.0.1`. Ready
means `Application startup complete.` in the log, or:

```bash
curl -sf http://localhost:8000/openapi.json > /dev/null && echo ready
```

Interactive docs are at `http://localhost:8000/docs`. Game sessions live in
memory; restarting the server forgets them.

## Verify: smoke script

```bash
bash .claude/skills/run-app/smoke.sh
```

Waits up to 30 s for the server (`SMOKE_TIMEOUT` changes that, `API_PORT`
targets another port), then creates a game, steps 7 days, and reads status
and forecast. Exit code 0 and a final `smoke: OK` mean the backend works end
to end. Needs only `curl` and a stdlib `python3`.

Manual equivalent of the first call:

```bash
curl -s -X POST http://localhost:8000/api/v1/games \
  -H 'Content-Type: application/json' \
  -d '{"fields":[{"field_id":"north","patches":[{"crop_key":"maize"}]}]}'
# -> {"game_id":"c0fb9970","phase":"planning","balance_credits":10000,"field_count":1}
```

Patch fields default to `loam_temperate` / `maize` / `netherlands_temperate`
with `area_fraction` 1.0. Routes: `POST /games`, `/games/{id}/step?days=N`,
`/start-season`, `/action`, `/action/preview`, `GET /games/{id}/status`,
`/forecast`, `/report`, plus `/plan`, `/revise`, `/save`, `/load`.

## Run the client

```bash
godot --path game &> /tmp/agrogame-game.log &
GODOT_PID=$!
```

A 1280x720 window opens. `project.godot` sets
`agrogame/debug/skip_menu=true`, so the main menu immediately calls
`POST /games` and switches to the farm view; `debug/auto_cutaway=true` then
runs a demo that applies three actions, steps 21 days, and opens the soil
cutaway. Ready looks like this in the log:

```
[GAME] created new game: e539b3ba
[API] step response: 1676911 bytes, code=200
```

`Error: could not reach backend` in the status label means the API is not
up on port 8000.

Godot prints `ERROR: Condition "det == 0" is true.` with
`at: invert (core/math/basis.cpp:47)` about 14 times per launch. The source
is `scripts/soil_view.gd`, where the cutaway open animation starts from
`scale = Vector3(1, 0, 1)`; the singular basis is harmless and the messages
can be ignored.

## Screenshot without screen-recording permission

`screencapture` needs a permission the terminal usually lacks. Godot's Movie
Maker mode renders to PNG frames instead:

```bash
mkdir -p /tmp/agrogame-frames
godot --path game --write-movie /tmp/agrogame-frames/shot.png \
  --fixed-fps 20 --quit-after 120 --resolution 1280x720
ls /tmp/agrogame-frames | tail -1   # shot00000119.png is the final frame
```

120 frames take about 18 s of wall time and cover the whole startup demo;
the last frame shows the farm view at Day 21 with the cutaway open. Look at
the frame: a flat empty field with `Creating game...` in the corner means
the client could not reach the backend.

## Stop

```bash
kill $GODOT_PID
pids=$(lsof -ti:8000 -sTCP:LISTEN); [ -n "$pids" ] && kill $pids   # reloader + worker
```

Prefer captured PIDs or the port over `pkill -f`, whose pattern can match
the shell that runs it.

## Related

- `make test-game` runs the GUT suite headlessly; `make lint-game` runs
  gdlint and gdformat.
- `poetry run pytest tests/test_api.py -x` exercises the API in-process.
- In zsh, `GID` is a read-only integer parameter; when scripting the API by
  hand, use another variable name for the game id.
