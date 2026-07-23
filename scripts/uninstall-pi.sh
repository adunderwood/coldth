#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -eq 0 ]]; then
  echo "Run this as the account that owns Coldth; the script uses sudo." >&2
  exit 1
fi

echo "This removes Coldth-managed system services and restores saved configs."
read -r -p "Continue? [y/N] " answer
[[ "$answer" =~ ^[Yy]$ ]] || exit 0

sudo systemctl disable --now coldth camilladsp 2>/dev/null || true
for service_path in \
  /etc/systemd/system/coldth.service \
  /etc/systemd/system/camilladsp.service; do
  if [[ -e "${service_path}.coldth-before" ]]; then
    sudo cp -a "${service_path}.coldth-before" "$service_path"
  elif grep -q "Managed by Coldth" "$service_path" 2>/dev/null; then
    sudo rm -f "$service_path"
  fi
done
if [[ -d /etc/systemd/system/camilladsp.service.d.coldth-before &&
      ! -e /etc/systemd/system/camilladsp.service.d ]]; then
  sudo mv /etc/systemd/system/camilladsp.service.d.coldth-before \
    /etc/systemd/system/camilladsp.service.d
fi

for path in /etc/shairport-sync.conf /etc/asound.conf; do
  if [[ -e "${path}.coldth-before" ]]; then
    sudo cp -a "${path}.coldth-before" "$path"
  elif grep -q "Managed by Coldth" "$path" 2>/dev/null; then
    sudo rm -f "$path"
  fi
done

if grep -q "Managed by Coldth" /etc/modules-load.d/snd-aloop.conf 2>/dev/null; then
  sudo rm -f /etc/modules-load.d/snd-aloop.conf
fi

sudo systemctl daemon-reload
sudo systemctl restart shairport-sync 2>/dev/null || true

echo "System integration removed. The repository and Coldth data were preserved."
