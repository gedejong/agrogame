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
#        SMOKE_LOG path (default: a temp file),
#        SMOKE_CHECK_LOG path: skip the run and only apply the liveness and
#        error checks to an existing log (used by client_smoke_selftest.sh)
#
# Stops on wall-clock time, not frame count: headless runs frames as fast as it
# can, so --quit-after would exit before the backend answers. No production
# client code serves this check; settings are pinned via a temporary
# game/override.cfg, which Godot reads natively.

set -euo pipefail

GODOT="${GODOT:-godot}"
TIMEOUT="${SMOKE_TIMEOUT:-60}"
GRACE="${SMOKE_GRACE:-5}"
API_URL="http://localhost:8000/openapi.json"
OVERRIDE="game/override.cfg"
# Printed by soil_view.gd once the flow overlay is built: proof the run
# reached the cutaway rather than passing vacuously on an empty field.
LIVENESS='^\[FLOW\] tubes='
# Engine and script errors as Godot 4 prints them.
ERROR_RE='^(USER |SCRIPT )?ERROR:'

# Strip ANSI escapes (CSI colour/cursor codes and OSC sequences) before any
# anchored match (#497). A colour code at line start would otherwise slip past
# '^...ERROR:' and the job would pass with errors present. Godot writes none to
# a file today; a future version, a pty runner or a wrapper could.
strip_ansi() {
    # CSI: ESC [ params(0x30-0x3F) intermediates(0x20-0x2F) final(0x40-0x7E),
    # per ECMA-48 5.4. The parameter class is spelled out as 0-9:;<=>? because
    # BSD sed rejects the range [0-?]; ':' carries ITU T.416 colon-SGR such as
    # ESC[38:5:196m, and '<=>' the private-parameter prefixes (#499 review).
    # OSC: ESC ] ... terminated by BEL or ST (ESC \).
    sed -E $'s#\x1B\\[[0-9:;<=>?]*[ -/]*[@-~]##g; s#\x1B\\][^\x07\x1B]*(\x07|\x1B\\\\)##g' "$1"
}

reached_cutaway() {
    strip_ansi "$1" | grep -qE "$LIVENESS"
}

# Exit status 1 and a per-class summary when the log holds runtime errors.
check_errors() {
    local clean
    clean=$(strip_ansi "$1")
    local errors
    errors=$(grep -cE "$ERROR_RE" <<<"$clean" || true)
    if [ "$errors" -gt 0 ]; then
        echo "Godot runtime errors in client smoke run: $errors" >&2
        grep -A1 -E "$ERROR_RE" <<<"$clean" | grep -v '^--$' | sort | uniq -c | sort -rn >&2
        echo "Log: $1" >&2
        return 1
    fi
}

if [ -n "${SMOKE_CHECK_LOG:-}" ]; then
    if ! reached_cutaway "$SMOKE_CHECK_LOG"; then
        echo "Log never reached the cutaway (no '[FLOW] tubes=')." >&2
        exit 1
    fi
    check_errors "$SMOKE_CHECK_LOG"
    echo "Log check: reached cutaway, 0 runtime errors."
    exit 0
fi

LOG="${SMOKE_LOG:-$(mktemp -t agrogame-smoke.XXXXXX)}"

if ! curl -sf -m 2 "$API_URL" >/dev/null; then
    echo "Backend not reachable at $API_URL. Start it first: make serve-api" >&2
    exit 2
fi
if [ -e "$OVERRIDE" ]; then
    echo "$OVERRIDE already exists; refusing to overwrite it." >&2
    exit 2
fi

godot_pid=""
override_created=false
cleanup() {
    if [ -n "$godot_pid" ] && kill -0 "$godot_pid" 2>/dev/null; then
        kill "$godot_pid" 2>/dev/null || true
        wait "$godot_pid" 2>/dev/null || true
    fi
    # Only remove the file this run created, never a pre-existing one.
    if $override_created; then
        rm -f "$OVERRIDE"
    fi
}
# Installed before override.cfg is written, so no signal can strand it (#497).
# Signals exit through the EXIT trap with the conventional 128+n status.
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

override_created=true
cat >"$OVERRIDE" <<'EOF'
[agrogame]

debug/skip_menu=true
debug/auto_cutaway=true
debug/flow_tubes_test=false
EOF

"$GODOT" --headless --path game >"$LOG" 2>&1 &
godot_pid=$!

reached=false
for _ in $(seq "$TIMEOUT"); do
    if reached_cutaway "$LOG"; then
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

check_errors "$LOG"

echo "Client smoke: reached cutaway, 0 runtime errors. Log: $LOG"
