#!/bin/bash

# Service wrapper inside deploy/
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$(realpath "$SCRIPT_DIR/..")"

exec "$PROJECT_DIR/scripts/service.sh" "$@"
curl -I http://<YOUR_PUBLIC_IP>