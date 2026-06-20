#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONTEXT_DIR="$(dirname "$PROJECT_DIR")"

docker build \
    -t astromech-server \
    -f "$PROJECT_DIR/Dockerfile" \
    "$CONTEXT_DIR"

docker run --rm \
    --net=host \
    --privileged \
    -v /var/run/dbus:/var/run/dbus \
    astromech-server
