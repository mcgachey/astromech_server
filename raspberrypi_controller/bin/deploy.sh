#!/usr/bin/env bash
# Deploy the controller service to a Raspberry Pi over ssh.
#
# Usage: bin/deploy.sh <hostname> [config-dir]
#
# Copies the sources the Docker build needs (this service and the
# astromech_boards SDK) to the Pi, installs Docker if missing, and runs
# bin/run_docker.sh there. Needs ssh access and sudo on the Pi.
#
# Config lives on the Pi in /etc/astromech-controller (default). If it has no
# droids.yml, the repo's config/droids.yml is installed; with [config-dir] given,
# that local directory's droids.yml is copied there first. Each droid the
# controller should drive needs a device_id in it.
set -euo pipefail

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
    echo "Usage: $0 <hostname> [config-dir]" >&2
    echo "  hostname:   Raspberry Pi to deploy to (ssh target, e.g. pi@r2t2)" >&2
    echo "  config-dir: optional local dir with droids.yml to install on the Pi" >&2
    exit 1
fi

HOST="$1"
LOCAL_CONFIG="${2:-}"
REMOTE_DIR="astromech-deploy"
REMOTE_CONFIG="/etc/astromech-controller"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"   # astromech_server/raspberrypi_controller
REPO_DIR="$(dirname "$PROJECT_DIR")"     # astromech_server

if [ -n "$LOCAL_CONFIG" ] && [ ! -f "$LOCAL_CONFIG/droids.yml" ]; then
    echo "error: $LOCAL_CONFIG/droids.yml not found" >&2
    exit 1
fi

SSH=(ssh -o BatchMode=no "$HOST")

echo "==> Checking Docker on $HOST"
"${SSH[@]}" 'command -v docker >/dev/null 2>&1 || {
    echo "Installing docker.io..."
    sudo apt-get update && sudo apt-get install -y --no-install-recommends docker.io
    sudo systemctl enable --now docker
}'

echo "==> Copying sources to $HOST:~/$REMOTE_DIR"
"${SSH[@]}" "rm -rf '$REMOTE_DIR/astromech_server' && mkdir -p '$REMOTE_DIR/astromech_server'"
tar -C "$REPO_DIR" \
    --exclude='__pycache__' --exclude='*.egg-info' --exclude='.pio' --exclude='.git' --exclude='node_modules' --exclude='dist' \
    -cf - raspberrypi_controller esp32/sdk/python config/droids.yml \
    | "${SSH[@]}" "tar -C '$REMOTE_DIR/astromech_server' -xf -"

if [ -n "$LOCAL_CONFIG" ]; then
    echo "==> Installing $LOCAL_CONFIG/droids.yml to $REMOTE_CONFIG"
    "${SSH[@]}" "sudo mkdir -p '$REMOTE_CONFIG' && sudo tee '$REMOTE_CONFIG/droids.yml' >/dev/null" \
        < "$LOCAL_CONFIG/droids.yml"
else
    echo "==> Checking $REMOTE_CONFIG/droids.yml"
    if ! "${SSH[@]}" "sudo test -f '$REMOTE_CONFIG/droids.yml'"; then
        echo "No config found: installing the repo's config/droids.yml to $REMOTE_CONFIG"
        "${SSH[@]}" "sudo mkdir -p '$REMOTE_CONFIG' && sudo cp '$REMOTE_DIR/astromech_server/config/droids.yml' '$REMOTE_CONFIG/droids.yml'"
    fi
fi

echo "==> Building and starting the container"
"${SSH[@]}" "sudo '$REMOTE_DIR/astromech_server/raspberrypi_controller/bin/run_docker.sh' '$REMOTE_CONFIG'"

echo "==> Done. Status:"
"${SSH[@]}" "sudo docker ps --filter name=astromech-controller --format '{{.Names}}: {{.Status}}'"
