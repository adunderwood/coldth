#!/usr/bin/env bash
set -u

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUTPUT="${1:-/tmp/coldth-diagnostics-$STAMP.txt}"
PYTHON="$REPO_DIR/venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3 || true)"
fi

exec > >(tee "$OUTPUT") 2>&1

section() {
  printf '\n[%s]\n' "$1"
}

section "Coldth diagnostic bundle"
printf 'created: %s\n' "$(date --iso-8601=seconds 2>/dev/null || date)"
printf 'host: %s\n' "$(hostname)"
printf 'kernel: %s\n' "$(uname -a)"

section "Service state"
for service in camilladsp coldth shairport-sync; do
  systemctl show "$service" \
    --property=Id,ActiveState,SubState,MainPID,ExecMainStatus,ActiveEnterTimestamp \
    --no-pager 2>&1 || true
done

section "Coldth canonical state"
curl -fsS http://127.0.0.1:8080/api/v1/state 2>&1 || true
printf '\n'

section "Coldth audio health"
curl -fsS http://127.0.0.1:8080/api/v1/health/audio 2>&1 || true
printf '\n'

section "CamillaDSP state and levels"
if [[ -n "$PYTHON" ]]; then
  "$PYTHON" - <<'PY' 2>&1 || true
import json
import websocket

connection = websocket.create_connection("ws://127.0.0.1:1234", timeout=2)
try:
    for command in (
        "GetVersion",
        "GetState",
        "GetStopReason",
        "GetCaptureSignalRms",
        "GetPlaybackSignalRms",
    ):
        connection.send(json.dumps(command))
        print(command, connection.recv())
finally:
    connection.close()
PY
else
  echo "No Python interpreter was found."
fi

section "ALSA loopback endpoints"
for status in \
  /proc/asound/Loopback/pcm0p/sub0/status \
  /proc/asound/Loopback/pcm0p/sub1/status \
  /proc/asound/Loopback/pcm1c/sub0/status \
  /proc/asound/Loopback/pcm1c/sub1/status
do
  printf '%s\n' "$status"
  if [[ -r "$status" ]]; then
    cat "$status"
  else
    echo "unavailable"
  fi
done

section "ALSA devices"
aplay -l 2>&1 || true
arecord -l 2>&1 || true

section "Recent CamillaDSP journal"
journalctl -u camilladsp --since "-30 minutes" --no-pager 2>&1 || true

section "Recent Coldth journal"
journalctl -u coldth --since "-30 minutes" --no-pager 2>&1 || true

section "Recent Shairport journal"
journalctl -u shairport-sync --since "-30 minutes" --no-pager 2>&1 || true

section "Recent kernel audio and USB messages"
journalctl -k --since "-30 minutes" --no-pager 2>&1 |
  grep -Ei 'alsa|audio|snd|usb|undervoltage|reset|disconnect' || true

section "Pi throttling"
if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd get_throttled 2>&1 || true
else
  echo "vcgencmd unavailable"
fi

section "Bundle location"
printf '%s\n' "$OUTPUT"
