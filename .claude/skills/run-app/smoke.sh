#!/usr/bin/env bash
# Smoke-test the AgroGame API: wait for readiness, create a game, step 7 days,
# read status and forecast. Exit code 0 means every call returned 200 with the
# expected JSON shape. Needs curl and a stdlib python3 on PATH.
#
#   API_PORT       port the server listens on (default 8000)
#   SMOKE_TIMEOUT  seconds to wait for the server before giving up (default 30)
set -euo pipefail

PORT="${API_PORT:-8000}"
TIMEOUT="${SMOKE_TIMEOUT:-30}"
ROOT="http://localhost:${PORT}"
BASE="${ROOT}/api/v1"

ready() { curl -sf "${ROOT}/openapi.json" > /dev/null; }

# The OpenAPI schema answers 200 as soon as the app has finished starting.
for ((i = 0; i < TIMEOUT * 2; i++)); do
  ready && break
  sleep 0.5
done
if ! ready; then
  echo "smoke: API not reachable on port ${PORT} after ${TIMEOUT}s (start it with: make serve-api)" >&2
  exit 1
fi

# Evaluate a Python expression over the decoded JSON body on stdin, bound to d.
json_get() { python3 -c "import sys, json; d = json.load(sys.stdin); print($1)"; }

echo "POST /games"
created=$(curl -sf -X POST "${BASE}/games" -H 'Content-Type: application/json' \
  -d '{"fields":[{"field_id":"north","patches":[{"soil_profile_key":"loam_temperate","crop_key":"maize","climate_key":"netherlands_temperate","area_fraction":1.0}]}],"starting_credits":10000}')
game_id=$(echo "$created" | json_get "d['game_id']")
echo "  game_id=${game_id} phase=$(echo "$created" | json_get "d['phase']") credits=$(echo "$created" | json_get "d['balance_credits']")"

echo "POST /games/${game_id}/step?days=7"
stepped=$(curl -sf -X POST "${BASE}/games/${game_id}/step?days=7")
echo "  date=$(echo "$stepped" | json_get "d['date']") patches=$(echo "$stepped" | json_get "len(d['patches'])") snapshots=$(echo "$stepped" | json_get "len(d['daily_snapshots'])")"

echo "GET /games/${game_id}/status"
echo "  balance_credits=$(curl -sf "${BASE}/games/${game_id}/status" | json_get "d['balance_credits']")"

echo "GET /games/${game_id}/forecast"
echo "  forecast_days=$(curl -sf "${BASE}/games/${game_id}/forecast" | json_get "len(d['forecast'])")"

echo "smoke: OK"
