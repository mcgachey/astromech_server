#!/usr/bin/env bash
# Gather debug information for the astromech-server container.
# Run on the host (r2t2) as a user with sudo access.

set -uo pipefail

CONTAINER="astromech-server"

hr() { echo; echo "=== $* ==="; }

hr "Container Status"
docker ps -a --filter "name=^/${CONTAINER}$" \
    --format "table {{.Names}}\t{{.Status}}\t{{.CreatedAt}}" 2>/dev/null \
    || echo "(docker not available)"

hr "Container Details"
docker inspect "$CONTAINER" --format \
    'Restart count: {{.RestartCount}}
Started at:    {{.State.StartedAt}}
Status:        {{.State.Status}}
Exit code:     {{.State.ExitCode}}' 2>/dev/null \
    || echo "(container not found)"

hr "BLE Adapter (host)"
hciconfig -a 2>/dev/null || echo "(hciconfig not available)"

hr "BLE Adapter (container)"
docker exec "$CONTAINER" hciconfig -a 2>/dev/null \
    || echo "(could not exec into container)"

LOG_PATH=$(docker inspect "$CONTAINER" --format '{{.LogPath}}' 2>/dev/null || true)
if [ -z "$LOG_PATH" ] || [ ! -f "$LOG_PATH" ]; then
    echo
    echo "Log file not accessible: ${LOG_PATH:-unknown}"
    exit 0
fi

_PARSE=$(mktemp /tmp/astromech_debug_XXXXXX.py)
trap 'rm -f "$_PARSE"' EXIT

cat > "$_PARSE" << 'PYEOF'
import sys, json

recent = []
beacon_failures = []
heartbeat = []
errors = []
http_failures = []

for raw in sys.stdin:
    try:
        msg = json.loads(raw)
        log = msg.get('log', '').rstrip('\n')
        ts  = msg.get('time', '')[:19]
    except Exception:
        log = raw.strip().replace('\x00', '')
        ts  = ''
    if not log:
        continue

    recent.append(log)
    low = log.lower()

    if '[beacon]' in log and ('fail' in low or 'error' in low):
        beacon_failures.append(f'{ts}  {log}')
    if '[heartbeat]' in log:
        heartbeat.append(f'{ts}  {log}')
    if any(k in log for k in ('Error', 'Traceback', 'Exception')):
        errors.append(f'{ts}  {log}')
    if '[http]' in log and 'failed' in low:
        http_failures.append(f'{ts}  {log}')

print(f'\n=== Recent Logs (last 50 of {len(recent)}) ===')
for l in recent[-50:]:
    print(l)

print(f'\n=== Beacon Failures ({len(beacon_failures)} total; showing last 10) ===')
for l in beacon_failures[-10:]:
    print(l)

print(f'\n=== Heartbeat Events ({len(heartbeat)} total) ===')
for l in heartbeat:
    print(l)

print(f'\n=== Errors / Tracebacks ===')
for l in errors[-30:]:
    print(l)

print(f'\n=== HTTP Failures ({len(http_failures)} total; showing last 20) ===')
for l in http_failures[-20:]:
    print(l)
PYEOF

hr "Logs"
echo "Reading from: $LOG_PATH"
sudo strings "$LOG_PATH" | python3 "$_PARSE"

echo
echo "Tip: to observe BLE events in real time, run: sudo btmon"
