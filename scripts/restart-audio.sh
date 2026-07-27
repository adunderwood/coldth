#!/usr/bin/env bash
set -euo pipefail

API_URL="${COLDTH_API_URL:-http://127.0.0.1:8080/api/v1/state}"
SHAIRPORT_STOPPED=0

restore_shairport_on_error() {
  if [[ $SHAIRPORT_STOPPED -eq 1 ]]; then
    sudo systemctl start shairport-sync >/dev/null 2>&1 || true
  fi
}
trap restore_shairport_on_error EXIT

echo "Stopping AirPlay input..."
sudo systemctl stop shairport-sync
SHAIRPORT_STOPPED=1

echo "Stopping Coldth..."
sudo systemctl stop coldth

echo "Restarting CamillaDSP..."
sudo systemctl restart camilladsp

for _ in {1..20}; do
  if command -v ss >/dev/null 2>&1 &&
     ss -ltn | grep -q '127.0.0.1:1234'; then
    break
  fi
  sleep 0.5
done

if ! command -v ss >/dev/null 2>&1 ||
   ! ss -ltn | grep -q '127.0.0.1:1234'; then
  echo "CamillaDSP did not open 127.0.0.1:1234." >&2
  exit 1
fi

echo "Starting Coldth..."
sudo systemctl start coldth

engine_running=0
for _ in {1..30}; do
  if curl -fsS "$API_URL" 2>/dev/null | grep -q '"engine":"running"'; then
    engine_running=1
    break
  fi
  sleep 0.5
done

if [[ $engine_running -ne 1 ]]; then
  echo "Coldth did not report a running audio engine." >&2
  echo "Run scripts/diagnose-audio.sh before making further changes." >&2
  exit 1
fi

echo "Starting AirPlay input..."
sudo systemctl start shairport-sync
SHAIRPORT_STOPPED=0
trap - EXIT

echo "Audio stack restarted in CamillaDSP → Coldth → Shairport order."
echo "Reconnect the AirPlay sender if it does not resume automatically."
