#!/usr/bin/env bash
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <config-dir>"
    echo "  config-dir: path to directory containing droids.yml"
    exit 1
fi

CONFIG_DIR="$(cd "$1" && pwd)"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTEXT_DIR="$(dirname "$PROJECT_DIR")"

docker build \
    -t astromech-server \
    -f "$PROJECT_DIR/Dockerfile" \
    "$CONTEXT_DIR"

docker rm -f astromech-server 2>/dev/null || true

docker run -d \
    --name astromech-server \
    --restart unless-stopped \
    --net=host \
    --privileged \
    -v /var/run/dbus:/var/run/dbus \
    -v "$CONFIG_DIR":/config:ro \
    astromech-server
