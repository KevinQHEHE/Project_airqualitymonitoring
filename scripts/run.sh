#!/bin/bash

# Quick test and start script (moved to scripts/)
set -e
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
VENV_PATH="$PROJECT_DIR/venv"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

test_app() {
    log_info "Testing Flask app creation..."
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    if python -c "from backend.app import create_app; create_app(); print('✓ Flask app test passed')" 2>/dev/null; then
        log_info "✓ Flask application can be created successfully"
        return 0
    else
        log_error "✗ Flask application failed to initialize"
        return 1
    fi
}

start_dev() {
    log_info "Starting development server..."
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    export FLASK_ENV=development
    export FLASK_DEBUG=1
    python wsgi.py
}

start_gunicorn() {
    log_info "Starting with Gunicorn..."
    cd "$PROJECT_DIR"
    source "$VENV_PATH/bin/activate"
    mkdir -p logs
    exec gunicorn \
        --config gunicorn.conf.py \
        --bind 127.0.0.1:8000 \
        --workers 2 \
        --timeout 30 \
        --log-level info \
        --access-logfile logs/access.log \
        --error-logfile logs/error.log \
        wsgi:app
}

usage() {
    echo "Usage: $0 [test|dev|gunicorn]"
}

case "${1:-}" in
    test)
        test_app
        ;;
    dev)
        test_app && start_dev
        ;;
    gunicorn)
        test_app && start_gunicorn
        ;;
    *)
        usage
        exit 1
        ;;
esac
