#!/bin/bash

# Start script (moved to scripts/)
set -e
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
VENV_PATH="$PROJECT_DIR/venv"
GUNICORN_CONF="$PROJECT_DIR/gunicorn.conf.py"
LOG_DIR="$PROJECT_DIR/logs"
PID_DIR="$PROJECT_DIR/logs"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

create_directories() {
    log_info "Creating necessary directories..."
    if [ ! -d "$LOG_DIR" ]; then
        mkdir -p "$LOG_DIR"
        log_info "Created log directory: $LOG_DIR"
    fi
    if [ ! -d "$PID_DIR" ]; then
        mkdir -p "$PID_DIR"
        log_info "Created PID directory: $PID_DIR"
    fi
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    if [ ! -d "$VENV_PATH" ]; then
        log_error "Virtual environment not found at $VENV_PATH"
        log_info "Run: python3 -m venv $VENV_PATH"
        exit 1
    fi
    if [ ! -f "$PROJECT_DIR/.env" ]; then
        log_warn ".env file not found. Copying from .env.sample"
        if [ -f "$PROJECT_DIR/.env.sample" ]; then
            cp "$PROJECT_DIR/.env.sample" "$PROJECT_DIR/.env"
            log_info "Please edit .env file with your configuration"
        else
            log_error ".env.sample file not found"
            exit 1
        fi
    fi
    if ! "$VENV_PATH/bin/python" -c "import gunicorn" 2>/dev/null; then
        log_error "Gunicorn not found in virtual environment"
        log_info "Run: $VENV_PATH/bin/pip install gunicorn"
        exit 1
    fi
}

start_app() {
    log_info "Starting Air Quality Monitoring System..."
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    exec "$VENV_PATH/bin/gunicorn" \
        --config "$GUNICORN_CONF" \
        wsgi:app
}

main() {
    log_info "Air Quality Monitoring System - Starting..."
    create_directories
    check_prerequisites
    start_app
}

cleanup() { log_info "Shutting down..."; exit 0; }
trap cleanup SIGTERM SIGINT
main "$@"
