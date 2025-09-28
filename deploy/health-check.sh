#!/bin/bash

set -uo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$SCRIPT_DIR/env" ]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/env"
fi

SERVICE_NAME=${SERVICE_NAME:-air-quality-monitoring}
NGINX_SERVICE=${NGINX_SERVICE:-nginx}
SERVICE_PORT=${SERVICE_PORT:-8000}
NGINX_PORT=${NGINX_PORT:-80}
PUBLIC_URL=${PUBLIC_URL:-}

if [ -z "$PUBLIC_URL" ]; then
    for candidate in "${PRIMARY_DOMAIN:-}" "${PUBLIC_DOMAIN:-}" "${PUBLIC_HOST:-}" "${PUBLIC_HOSTNAME:-}"; do
        if [ -n "$candidate" ]; then
            if [[ "$candidate" == http* ]]; then
                PUBLIC_URL="$candidate"
            else
                PUBLIC_URL="https://$candidate"
            fi
            break
        fi
    done
fi

STATUS=0

log_info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO:${NC} $1"
}

log_pass() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')] OK:${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARN:${NC} $1"
}

log_fail() {
    STATUS=1
    echo -e "${RED}[$(date +'%H:%M:%S')] FAIL:${NC} $1"
}

check_service() {
    local service="$1"
    local label="$2"
    if sudo systemctl is-active --quiet "$service"; then
        log_pass "$label (service: $service) is running"
    else
        log_fail "$label (service: $service) is NOT running"
    fi
}

check_http() {
    local url="$1"
    local label="$2"
    if response=$(curl -fsS --max-time 10 "$url" 2>/dev/null); then
        log_pass "$label reachable at $url"
    else
        log_fail "$label unreachable at $url"
    fi
}

header() {
    echo
    echo "============================================="
    echo "$1"
    echo "============================================="
}

header "SERVICE STATUS"
check_service "$SERVICE_NAME" "Application"
check_service "$NGINX_SERVICE" "Nginx proxy"

header "API HEALTH"
check_http "http://127.0.0.1:${SERVICE_PORT}/api/health" "Gunicorn (direct)"
check_http "http://localhost/api/health" "Nginx (HTTP)"

if [ -n "$PUBLIC_URL" ]; then
    if [[ "$PUBLIC_URL" != http*://* ]]; then
        PUBLIC_URL="https://$PUBLIC_URL"
    fi
    header "PUBLIC ACCESS"
    check_http "${PUBLIC_URL%/}/api/health" "Public endpoint"
else
    log_warn "No PUBLIC_URL configured. Skipping public endpoint check."
fi

exit $STATUS