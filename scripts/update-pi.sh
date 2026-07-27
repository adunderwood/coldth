#!/usr/bin/env bash
set -euo pipefail

PULL=1

usage() {
  cat <<'EOF'
Update an existing Raspberry Pi Coldth installation.

Usage: ./scripts/update-pi.sh [--no-pull]

  --no-pull  Install the current checkout without fetching Git changes.

The command refuses to pull over local changes, reinstalls Coldth into the
same repository-owned virtual environment used by systemd, restarts only the
Coldth service, and verifies that the HTTP API returns.
EOF
}

while (($#)); do
  case "$1" in
    --no-pull) PULL=0 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [[ $EUID -eq 0 ]]; then
  echo "Run this updater as the account that owns the Coldth checkout." >&2
  exit 1
fi

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$REPO_DIR/venv"
API_URL="${COLDTH_API_URL:-http://127.0.0.1:8080/api/v1/state}"

if [[ ! -f "$REPO_DIR/pyproject.toml" ]] ||
   [[ ! -x "$VENV_DIR/bin/python" ]]; then
  echo "Coldth or its virtual environment is missing at $REPO_DIR." >&2
  echo "Run ./scripts/install-pi.sh for a new installation." >&2
  exit 1
fi

cd "$REPO_DIR"

if [[ $PULL -eq 1 ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "The Coldth checkout has local changes; refusing to pull over them." >&2
    echo "Commit, stash, or discard those changes, then run this command again." >&2
    exit 1
  fi
  echo "Fetching the latest Coldth revision..."
  git pull --ff-only
fi

echo "Installing the checkout into $VENV_DIR..."
"$VENV_DIR/bin/python" -m pip install "$REPO_DIR"

echo "Restarting Coldth..."
sudo systemctl restart coldth

for _ in {1..30}; do
  if curl -fsS "$API_URL" >/dev/null 2>&1; then
    echo "Coldth updated successfully: $(git rev-parse --short HEAD)"
    exit 0
  fi
  sleep 0.5
done

echo "Coldth did not return from the update." >&2
echo "Check: systemctl status coldth --no-pager -l" >&2
exit 1
