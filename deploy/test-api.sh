#!/bin/bash

# Test wrapper inside deploy/
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$(realpath "$SCRIPT_DIR/..")"

exec "$PROJECT_DIR/scripts/test-api.sh" "$@"
