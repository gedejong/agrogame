# AgroGame

[![Python CI](https://github.com/databuildcompany/agrogame/actions/workflows/python.yml/badge.svg)](https://github.com/databuildcompany/agrogame/actions/workflows/python.yml)
[![Godot CI](https://github.com/databuildcompany/agrogame/actions/workflows/godot.yml/badge.svg)](https://github.com/databuildcompany/agrogame/actions/workflows/godot.yml)

Soil-plant-atmosphere farming simulation game. Monorepo with Python
simulation backend and Godot 4 game client.

- Jira project: AGRO
- Spec: https://data-build-company.atlassian.net/wiki/spaces/~712020da4bf39b64bd41f6b7a8c0fcf6663b39/pages/307167238/Soil+Plant+Atmosphere+Simulation+Farm+Game

## Monorepo Structure

```
agrogame/          Python simulation engine
game/              Godot 4 game client (GDScript)
data/              Crop/climate/soil/economy presets
docs/              MkDocs documentation + ADRs
tests/             Python tests
scripts/           Analysis and utility scripts
```

## Python Backend

Prereqs: Python >=3.10, Poetry >=2.1

```bash
poetry install
poetry run pytest              # run tests
make serve-api                 # start FastAPI at localhost:8000
```

## Godot Game Client

Prereqs: Godot 4.3+

```bash
# Open in Godot editor
cd game && godot project.godot

# Or build from CLI
make build-game
```

The game client communicates with the Python backend via REST API
at `localhost:8000`. Start the API server first, then run the game.

