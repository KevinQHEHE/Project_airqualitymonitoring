#!/bin/bash

# Service wrapper inside deploy/
set -e

SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PROJECT_DIR="$(realpath "$SCRIPT_DIR/..")"

# Source deploy/env if present (server-specific overrides)
if [ -f "$SCRIPT_DIR/env" ]; then
	# shellcheck source=/dev/null
	source "$SCRIPT_DIR/env"
fi

exec "$PROJECT_DIR/scripts/service.sh" "$@"