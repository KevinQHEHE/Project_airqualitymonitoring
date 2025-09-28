#!/bin/bash

# Deploy wrapper inside deploy/ (calls project-level deployment logic)
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$(realpath "$SCRIPT_DIR/..")"
echo "Using PROJECT_DIR: $PROJECT_DIR"

exec "$PROJECT_DIR/scripts/deploy.sh" "$@"
