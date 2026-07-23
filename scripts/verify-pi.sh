#!/usr/bin/env bash
set -u

failures=0
ok() { printf 'ok    %s\n' "$1"; }
bad() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }

for command in camilladsp arecord shairport-sync; do
  command -v "$command" >/dev/null 2>&1 &&
    ok "$command is installed" ||
    bad "$command is not installed"
done

for service in camilladsp coldth shairport-sync; do
  systemctl is-active --quiet "$service" &&
    ok "$service is running" ||
    bad "$service is not running"
done

grep -q '^snd-aloop$' /etc/modules-load.d/snd-aloop.conf 2>/dev/null &&
  ok "snd-aloop is persistent" ||
  bad "snd-aloop module-load configuration is missing"

[[ -d /proc/asound/Loopback ]] &&
  ok "ALSA Loopback is loaded" ||
  bad "ALSA Loopback is not loaded"

if command -v ss >/dev/null 2>&1 &&
   ss -ltn | grep -q '127.0.0.1:1234'; then
  ok "CamillaDSP WebSocket is listening on 1234"
else
  bad "CamillaDSP WebSocket is not listening on 1234"
fi

if curl -fsS http://127.0.0.1:8080/api/state >/dev/null 2>&1; then
  ok "Coldth API is responding on 8080"
else
  bad "Coldth API is not responding on 8080"
fi

if [[ $failures -eq 0 ]]; then
  echo "Coldth base services pass."
else
  echo "$failures check(s) failed."
fi

echo "Audio endpoints become RUNNING only while an AirPlay stream is connected."
exit "$failures"
