#!/usr/bin/env bash
# Headless client smoke run: fail on any Godot runtime error (issue #489).
#
# Godot runtime errors fail neither the build nor GUT, so they surface only in
# the client's stdout. #484 regressed silently for two months that way. This
# runs the real client headless against a live backend until it reaches the
# soil cutaway, then fails on any ERROR line in the log.
#
# Usage: bash game/tests/client_smoke.sh   (run from the repo root, backend up)
# Env:   GODOT (default: godot), SMOKE_TIMEOUT seconds (default: 60),
#        SMOKE_GRACE seconds after liveness (default: 5),
#        SMOKE_LOG path (default: a temp file)
#
# Stops on wall-clock time, not frame count: headless runs frames as fast as it
# can, so --quit-after would exit before the backend answers. No production
# client code serves this check; settings are pinned via a temporary
# game/override.cfg, which Godot reads natively.

set -euo pipefail

GODOT="${GODOT:-godot}"
TIMEOUT="${SMOKE_TIMEOUT:-60}"
GRACE="${SMOKE_GRACE:-5}"
LOG="${SMOKE_LOG:-$(mktemp -t agrogame-smoke.XXXXXX)}"
API_URL="http://localhost:8000/openapi.json"
OVERRIDE="game/override.cfg"
# Printed by soil_view.gd once the flow overlay is built: proof the run
# reached the cutaway rather than passing vacuously on an empty field.
LIVENESS='^\[FLOW\] tubes='
# Engine and script errors as Godot 4 prints them.
ERROR_RE='^(USER |SCRIPT )?ERROR:'

if ! curl -sf -m 2 "$API_URL" >/dev/null; then
    echo "Backend not reachable at $API_URL. Start it first: make serve-api" >&2
    exit 2
fi
if [ -e "$OVERRIDE" ]; then
    echo "$OVERRIDE already exists; refusing to overwrite it." >&2
    exit 2
fi

cat >"$OVERRIDE" <<'EOF'
[agrogame]

debug/skip_menu=true
debug/auto_cutaway=true
debug/flow_tubes_test=false
EOF

godot_pid=""
cleanup() {
    if [ -n "$godot_pid" ] && kill -0 "$godot_pid" 2>/dev/null; then
        kill "$godot_pid" 2>/dev/null || true
        wait "$godot_pid" 2>/dev/null || true
    fi
    rm -f "$OVERRIDE"
}
trap cleanup EXIT

"$GODOT" --headless --path game >"$LOG" 2>&1 &
godot_pid=$!

reached=false
for _ in $(seq "$TIMEOUT"); do
    if grep -qE "$LIVENESS" "$LOG"; then
        reached=true
        break
    fi
    if ! kill -0 "$godot_pid" 2>/dev/null; then
        break
    fi
    sleep 1
done
if $reached; then
    # Errors from the overlay's first physics tick land just after liveness.
    sleep "$GRACE"
fi
if ! kill -0 "$godot_pid" 2>/dev/null; then
    wait "$godot_pid" || true
    if ! $reached; then
        echo "Client exited before reaching the cutaway. Log: $LOG" >&2
        tail -n 30 "$LOG" >&2
        exit 1
    fi
fi
cleanup
godot_pid=""

if ! $reached; then
    echo "Client never reached the cutaway within ${TIMEOUT}s (no '[FLOW] tubes=')." >&2
    echo "Log: $LOG" >&2
    tail -n 30 "$LOG" >&2
    exit 1
fi

errors=$(grep -cE "$ERROR_RE" "$LOG" || true)
if [ "$errors" -gt 0 ]; then
    echo "Godot runtime errors in client smoke run: $errors" >&2
    grep -A1 -E "$ERROR_RE" "$LOG" | grep -v '^--$' | sort | uniq -c | sort -rn >&2
    echo "Log: $LOG" >&2
    exit 1
fi

echo "Client smoke: reached cutaway, 0 runtime errors. Log: $LOG"
