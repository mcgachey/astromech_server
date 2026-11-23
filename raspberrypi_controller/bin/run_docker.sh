#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <config-dir>"
    echo "  config-dir: path to directory containing droids.yml"
    exit 1
fi

CONFIG_DIR="$(cd "$1" && pwd)"

# Board names, notes and logs persist here on the host across restarts and rebuilds.
DATA_DIR="${CONTROLLER_DATA:-/var/lib/astromech-controller}"
mkdir -p "$DATA_DIR"

# Firmware images pushed by `make install` in esp32/ (see esp32/install.conf.example).
# The ssh user that runs it must be able to write here.
FIRMWARE_DIR="${FIRMWARE_DIR:-/var/lib/astromech-controller/firmware}"
mkdir -p "$FIRMWARE_DIR"
if [ -n "${SUDO_USER:-}" ]; then chown "$SUDO_USER" "$FIRMWARE_DIR"; fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"   # astromech_server/raspberrypi_controller
REPO_DIR="$(dirname "$PROJECT_DIR")"     # astromech_server
CONTEXT_DIR="$(dirname "$REPO_DIR")"     # parent holding astromech_server/

docker build \
    -t astromech-controller \
    -f "$PROJECT_DIR/Dockerfile" \
    "$CONTEXT_DIR"

docker rm -f astromech-controller 2>/dev/null || true

# /dev is mounted so the board's serial node (and re-plugs of it) is visible.
docker run -d \
    --name astromech-controller \
    --restart unless-stopped \
    --net=host \
    --privileged \
    -v /dev:/dev \
    -v /run/dbus:/run/dbus \
    -v "$CONFIG_DIR":/config:ro \
    -v "$DATA_DIR":/data \
    -v "$FIRMWARE_DIR":/firmware:ro \
    astromech-controller
