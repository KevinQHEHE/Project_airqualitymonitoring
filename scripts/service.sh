#!/bin/bash

# Service management script (moved to scripts/)
set -e
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
SERVICE_NAME="air-quality-monitoring"
SERVICE_FILE="$PROJECT_DIR/$SERVICE_NAME.service"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }

install_service() {
    log_step "Installing systemd service..."
    if [ ! -f "$SERVICE_FILE" ]; then
        log_error "Service file not found: $SERVICE_FILE"
        exit 1
    fi
    sudo cp "$SERVICE_FILE" "/etc/systemd/system/"
    log_info "Service file copied to /etc/systemd/system/"
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    log_info "Service enabled for auto-start"
    log_info "✓ Service installation completed"
}

start_service() { log_step "Starting service..."; sudo systemctl start "$SERVICE_NAME"; log_info "✓ Service started"; }
stop_service() { log_step "Stopping service..."; sudo systemctl stop "$SERVICE_NAME"; log_info "✓ Service stopped"; }
restart_service() { log_step "Restarting service..."; sudo systemctl restart "$SERVICE_NAME"; log_info "✓ Service restarted"; }
status_service() { log_step "Service status:"; sudo systemctl status "$SERVICE_NAME" --no-pager -l; }
logs_service() { log_step "Service logs (last 50 lines):"; sudo journalctl -u "$SERVICE_NAME" -n 50 --no-pager; }
follow_logs() { log_step "Following service logs (Ctrl+C to stop):"; sudo journalctl -u "$SERVICE_NAME" -f; }
uninstall_service() {
    log_step "Uninstalling service..."
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    sudo rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    sudo systemctl daemon-reload
    log_info "✓ Service uninstalled"
}

usage() {
    echo "Usage: $0 [install|start|stop|restart|status|logs|follow|uninstall]"
}

case "${1:-}" in
    install) install_service ;; start) start_service ;; stop) stop_service ;; restart) restart_service ;; status) status_service ;; logs) logs_service ;; follow) follow_logs ;; uninstall) uninstall_service ;; *) usage; exit 1 ;;
esac
