#!/usr/bin/env bash
set -euo pipefail

CAMILLA_VERSION="${CAMILLA_VERSION:-3.0.1}"
WITH_ANALYZER=1
ARTWORK_MODE="ask"
SKIP_PACKAGES=0

usage() {
  cat <<'EOF'
Install Coldth on a dedicated Raspberry Pi.

Usage: ./scripts/install-pi.sh [options]

  --with-analyzer  Enable the ten-band FFT and ALSA fan-out (the default).
  --without-analyzer
                   Install without spectrum analysis (troubleshooting mode).
  --with-artwork   Request and display AirPlay album artwork.
  --without-artwork
                   Do not request AirPlay album artwork.
  --skip-packages  Do not run apt or download CamillaDSP.

When neither artwork flag is supplied, an interactive installation asks.
Non-interactive installation defaults to no artwork.

Environment:
  CAMILLA_VERSION  CamillaDSP version to install when missing (default: 3.0.1).
  COLDTH_PLAYBACK_DEVICE
                   ALSA output device. When unset, one USB playback device is
                   selected automatically, then the Pi headphone output.
  COLDTH_SAMPLE_RATE
                   Audio processing rate (USB default: 48000; Pi: 44100).
  COLDTH_CHUNKSIZE CamillaDSP chunk size (USB default: 2048; Pi: 1024).
EOF
}

while (($#)); do
  case "$1" in
    --with-analyzer) WITH_ANALYZER=1 ;;
    --without-analyzer) WITH_ANALYZER=0 ;;
    --with-artwork) ARTWORK_MODE="yes" ;;
    --without-artwork) ARTWORK_MODE="no" ;;
    --skip-packages) SKIP_PACKAGES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ "$ARTWORK_MODE" == "ask" ]]; then
  if [[ -t 0 ]]; then
    read -r -p "Enable album artwork from AirPlay senders? [y/N] " reply
    case "$reply" in
      y|Y|yes|YES|Yes) ARTWORK_MODE="yes" ;;
      *) ARTWORK_MODE="no" ;;
    esac
  else
    ARTWORK_MODE="no"
  fi
fi

if [[ $EUID -eq 0 ]]; then
  echo "Run this installer as the account that owns the Coldth checkout, not as root." >&2
  echo "It will use sudo for system changes." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_USER="$(id -un)"
INSTALL_GROUP="$(id -gn)"
USER_HOME="$(getent passwd "$INSTALL_USER" | cut -d: -f6)"
VENV_DIR="$REPO_DIR/venv"
DATA_DIR="$REPO_DIR/data"
CAMILLA_DIR="$USER_HOME/camilladsp"
PLAYBACK_DEVICE="${COLDTH_PLAYBACK_DEVICE:-}"
SAMPLE_RATE="${COLDTH_SAMPLE_RATE:-}"
CHUNKSIZE="${COLDTH_CHUNKSIZE:-}"
PLAYBACK_SOURCE="explicit"

# shellcheck source=scripts/lib/audio-device.sh
source "$REPO_DIR/scripts/lib/audio-device.sh"

if [[ ! -f "$REPO_DIR/pyproject.toml" ]]; then
  echo "Could not identify the Coldth repository at $REPO_DIR" >&2
  exit 1
fi
if [[ ! -r /proc/device-tree/model ]] ||
   ! tr -d '\0' </proc/device-tree/model | grep -qi "Raspberry Pi"; then
  echo "This installer is intended for Raspberry Pi OS." >&2
  exit 1
fi

sudo -v

if [[ $SKIP_PACKAGES -eq 0 ]]; then
  sudo apt-get update
  sudo apt-get install -y \
    alsa-utils ca-certificates curl git nginx python3 python3-pip python3-venv \
    shairport-sync
fi

if [[ -z "$PLAYBACK_DEVICE" ]]; then
  mapfile -t usb_playback_devices < <(
    aplay -l 2>/dev/null | coldth_usb_playback_devices
  )
  if [[ ${#usb_playback_devices[@]} -eq 1 ]]; then
    PLAYBACK_DEVICE="${usb_playback_devices[0]}"
    PLAYBACK_SOURCE="usb"
    echo "Detected USB playback device: $PLAYBACK_DEVICE"
  elif [[ ${#usb_playback_devices[@]} -gt 1 ]]; then
    echo "Multiple USB playback devices were detected:" >&2
    printf '  %s\n' "${usb_playback_devices[@]}" >&2
    echo "Rerun with COLDTH_PLAYBACK_DEVICE set to the intended device." >&2
    exit 1
  elif aplay -L 2>/dev/null | grep -q 'Headphones'; then
    PLAYBACK_DEVICE="hw:Headphones,0"
    PLAYBACK_SOURCE="headphones"
    echo "Detected Raspberry Pi headphone output: $PLAYBACK_DEVICE"
  else
    echo "No supported USB or Raspberry Pi headphone playback device was detected." >&2
    echo "Available playback hardware:" >&2
    aplay -l >&2 || true
    echo "Connect a DAC or rerun with COLDTH_PLAYBACK_DEVICE set explicitly." >&2
    exit 1
  fi
fi

if [[ -z "$SAMPLE_RATE" ]]; then
  [[ "$PLAYBACK_SOURCE" == "usb" ]] && SAMPLE_RATE=48000 || SAMPLE_RATE=44100
fi
if [[ -z "$CHUNKSIZE" ]]; then
  [[ "$PLAYBACK_SOURCE" == "usb" ]] && CHUNKSIZE=2048 || CHUNKSIZE=1024
fi
if [[ ! "$SAMPLE_RATE" =~ ^[1-9][0-9]*$ ]]; then
  echo "COLDTH_SAMPLE_RATE must be a positive integer." >&2
  exit 1
fi
if [[ ! "$CHUNKSIZE" =~ ^[1-9][0-9]*$ ]]; then
  echo "COLDTH_CHUNKSIZE must be a positive integer." >&2
  exit 1
fi

echo "Coldth repository: $REPO_DIR"
echo "Service account:    $INSTALL_USER"
echo "Playback device:    $PLAYBACK_DEVICE ($PLAYBACK_SOURCE)"
echo "Sample rate:        $SAMPLE_RATE"
echo "Chunk size:         $CHUNKSIZE"
echo "Analyzer:           $([[ $WITH_ANALYZER -eq 1 ]] && echo enabled || echo disabled)"
echo "Album artwork:      $([[ "$ARTWORK_MODE" == "yes" ]] && echo enabled || echo disabled)"

install_camilladsp() {
  if command -v camilladsp >/dev/null 2>&1; then
    CAMILLA_BIN="$(command -v camilladsp)"
    echo "Using existing CamillaDSP: $CAMILLA_BIN"
    return
  fi
  if [[ $SKIP_PACKAGES -eq 1 ]]; then
    echo "CamillaDSP is missing and --skip-packages was supplied." >&2
    exit 1
  fi

  local machine asset archive temp_dir binary
  machine="$(uname -m)"
  case "$machine" in
    aarch64|arm64) asset="camilladsp-linux-aarch64.tar.gz" ;;
    armv7l) asset="camilladsp-linux-armv7.tar.gz" ;;
    *)
      echo "Unsupported Pi architecture: $machine" >&2
      exit 1
      ;;
  esac

  temp_dir="$(mktemp -d)"
  archive="$temp_dir/$asset"
  echo "Downloading CamillaDSP $CAMILLA_VERSION for $machine..."
  curl -fL \
    "https://github.com/HEnquist/camilladsp/releases/download/v${CAMILLA_VERSION}/${asset}" \
    -o "$archive"
  tar -xzf "$archive" -C "$temp_dir"
  binary="$(find "$temp_dir" -type f -name camilladsp -perm -u+x -print -quit)"
  if [[ -z "$binary" ]]; then
    echo "The CamillaDSP archive did not contain an executable." >&2
    exit 1
  fi
  sudo install -m 0755 "$binary" /usr/local/bin/camilladsp
  rm -rf "$temp_dir"
  CAMILLA_BIN="/usr/local/bin/camilladsp"
}

CAMILLA_BIN=""
install_camilladsp

python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install "$REPO_DIR"
mkdir -p "$DATA_DIR" "$CAMILLA_DIR"

sudo usermod -aG audio "$INSTALL_USER"
if id shairport-sync >/dev/null 2>&1; then
  sudo usermod -aG audio shairport-sync
fi

sudo install -m 0644 "$REPO_DIR/deploy/snd-aloop.conf" \
  /etc/modules-load.d/snd-aloop.conf
sudo modprobe snd-aloop

backup_once() {
  local path="$1"
  if [[ -e "$path" && ! -e "${path}.coldth-before" ]]; then
    sudo cp -a "$path" "${path}.coldth-before"
  fi
}

backup_once /etc/shairport-sync.conf
backup_once /etc/systemd/system/camilladsp.service
backup_once /etc/systemd/system/coldth.service
backup_once /etc/nginx/sites-enabled/default

SHAIRPORT_DEVICE="hw:Loopback,0,0"
if [[ "$SAMPLE_RATE" != "44100" ]]; then
  SHAIRPORT_DEVICE="plughw:CARD=Loopback,DEV=0"
fi
ANALYZER_ENV=""
if [[ $WITH_ANALYZER -eq 1 ]]; then
  backup_once /etc/asound.conf
  sudo install -m 0644 "$REPO_DIR/deploy/asound-analyzer.conf.example" \
    /etc/asound.conf
  SHAIRPORT_DEVICE="coldth_fanout"
  ANALYZER_ENV="Environment=COLDTH_ANALYZER_DEVICE=hw:Loopback,1,1"
elif [[ -f /etc/asound.conf ]] &&
     grep -q "Managed by Coldth" /etc/asound.conf; then
  if [[ -e /etc/asound.conf.coldth-before ]]; then
    sudo cp -a /etc/asound.conf.coldth-before /etc/asound.conf
  else
    sudo rm /etc/asound.conf
  fi
fi

sudo tee /etc/shairport-sync.conf >/dev/null <<EOF
// Managed by Coldth. Original saved as shairport-sync.conf.coldth-before.
general = {
    name = "Coldth";
    output_backend = "alsa";
    statistics = "yes";
};

alsa = {
    output_device = "$SHAIRPORT_DEVICE";
    output_rate = 44100;
    output_format = "S16";
};

metadata = {
    enabled = "yes";
    include_cover_art = "$ARTWORK_MODE";
    pipe_name = "/tmp/shairport-sync-metadata";
};
EOF

sudo tee /etc/systemd/system/camilladsp.service >/dev/null <<EOF
# Managed by Coldth.
[Unit]
Description=CamillaDSP for Coldth
After=sound.target
Before=coldth.service

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
SupplementaryGroups=audio
WorkingDirectory=$USER_HOME
ExecStart=$CAMILLA_BIN -s $CAMILLA_DIR/statefile.yml -w -g0 -p 1234
Restart=always
RestartSec=2
StandardOutput=journal
StandardError=journal
SyslogIdentifier=camilladsp
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$CAMILLA_DIR

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/coldth.service >/dev/null <<EOF
# Managed by Coldth.
[Unit]
Description=Coldth web equalizer
Wants=network-online.target camilladsp.service
After=network-online.target camilladsp.service

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
SupplementaryGroups=audio
WorkingDirectory=$REPO_DIR
Environment=COLDTH_DATA_DIR=$DATA_DIR
Environment=COLDTH_HOST=127.0.0.1
Environment=COLDTH_PORT=8080
Environment=COLDTH_CAMILLADSP_URL=ws://127.0.0.1:1234
Environment=COLDTH_SHAIRPORT_METADATA_PIPE=/tmp/shairport-sync-metadata
Environment=COLDTH_CAPTURE_DEVICE=hw:Loopback,1,0
Environment=COLDTH_PLAYBACK_DEVICE=$PLAYBACK_DEVICE
Environment=COLDTH_CAPTURE_FORMAT=S16LE
Environment=COLDTH_PLAYBACK_FORMAT=S16LE
Environment=COLDTH_SAMPLE_RATE=$SAMPLE_RATE
Environment=COLDTH_CHUNKSIZE=$CHUNKSIZE
$ANALYZER_ENV
ExecStart=$VENV_DIR/bin/coldth
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
# Coldth and Shairport Sync must see the same metadata FIFO in /tmp.
PrivateTmp=false
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$REPO_DIR

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$REPO_DIR/deploy/nginx.conf" \
  /etc/nginx/sites-available/coldth
sudo ln -sfn /etc/nginx/sites-available/coldth \
  /etc/nginx/sites-enabled/coldth
if [[ -L /etc/nginx/sites-enabled/default ]]; then
  sudo unlink /etc/nginx/sites-enabled/default
fi
sudo nginx -t

sudo mkdir -p /etc/systemd/system/shairport-sync.service.d
sudo install -m 0644 \
  "$REPO_DIR/deploy/shairport-sync-coldth.conf.example" \
  /etc/systemd/system/shairport-sync.service.d/coldth-ordering.conf

# A full unit in /etc supersedes the packaged unit. Old drop-ins can otherwise
# override its ExecStart unexpectedly.
if [[ -d /etc/systemd/system/camilladsp.service.d ]]; then
  if [[ ! -e /etc/systemd/system/camilladsp.service.d.coldth-before ]]; then
    sudo mv /etc/systemd/system/camilladsp.service.d \
      /etc/systemd/system/camilladsp.service.d.coldth-before
  else
    echo "Existing CamillaDSP drop-ins were not changed because a backup already exists." >&2
  fi
fi

sudo systemctl daemon-reload
sudo systemctl enable camilladsp coldth nginx shairport-sync
"$REPO_DIR/scripts/restart-audio.sh"
sudo systemctl restart nginx

if [[ "$ARTWORK_MODE" == "yes" ]]; then
  artwork_saved=0
  for _ in {1..10}; do
    if curl -fsS -X PUT \
      -H "Content-Type: application/json" \
      --data '{"metadata":true,"artwork":true}' \
      http://127.0.0.1:8080/api/v1/settings/privacy >/dev/null; then
      artwork_saved=1
      break
    fi
    sleep 1
  done
  if [[ $artwork_saved -eq 0 ]]; then
    echo "Warning: Shairport artwork is enabled, but Coldth's artwork preference could not be saved." >&2
    echo "Open /settings and enable 'Use album artwork' after installation." >&2
  fi
fi

echo
"$REPO_DIR/scripts/verify-pi.sh" || true
echo
echo "Installation complete."
echo "Reconnect AirPlay, then open http://$(hostname -I | awk '{print $1}')"
if [[ $WITH_ANALYZER -eq 1 ]]; then
  echo "The ten-band display becomes live after AirPlay opens both loopback feeds."
fi
