#!/bin/bash

# Air Quality Monitoring System - Complete Deployment Script (moved to scripts/)
# Computes project root dynamically so it works when invoked from anywhere.

set -e

# Project root (one level up from this script)
PROJECT_DIR="$(dirname "$(dirname "$(realpath "$0")")")"
VENV_PATH="$PROJECT_DIR/venv"
NGINX_CONF="$PROJECT_DIR/nginx.conf"
SERVICE_NAME="air-quality-monitoring"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_header() { echo -e "${PURPLE}[DEPLOY]${NC} $1"; }

# Check prerequisites
check_prerequisites() {
    log_step "Checking prerequisites..."
    if [ ! -f "$PROJECT_DIR/wsgi.py" ]; then
        log_error "Not in project directory or wsgi.py not found"
        exit 1
    fi
    if [ ! -d "$VENV_PATH" ]; then
        log_error "Virtual environment not found: $VENV_PATH"
        exit 1
    fi
    if ! "$VENV_PATH/bin/python" -c "import gunicorn" 2>/dev/null; then
        log_error "Gunicorn not installed in virtual environment"
        exit 1
    fi
    if ! command -v nginx &> /dev/null; then
        log_warn "Nginx not installed. Install with: sudo apt install nginx"
    fi
    log_info "✓ Prerequisites check passed"
}

setup_directories() {
    log_step "Setting up directories and permissions..."
    mkdir -p "$PROJECT_DIR/logs"
    mkdir -p "$PROJECT_DIR/backend/app/static"
    log_info "✓ Directories created"
}

test_application() {
    log_step "Testing Flask application..."
    cd "$PROJECT_DIR"
    if source "$VENV_PATH/bin/activate" && python -c "from backend.app import create_app; create_app(); print('✓ Test passed')" 2>/dev/null; then
        log_info "✓ Flask application test passed"
        return 0
    else
        log_error "✗ Flask application test failed"
        return 1
    fi
}

setup_nginx() {
    log_step "Setting up Nginx configuration..."
    if [ ! -f "$NGINX_CONF" ]; then
        log_error "Nginx configuration file not found: $NGINX_CONF"
        exit 1
    fi
    if ! command -v nginx &> /dev/null; then
        log_warn "Nginx not installed. Skipping nginx configuration."
        return 0
    fi
    if [ -f "/etc/nginx/sites-available/default" ]; then
        sudo cp /etc/nginx/sites-available/default /etc/nginx/sites-available/default.backup.$(date +%Y%m%d_%H%M%S)
        log_info "✓ Existing nginx config backed up"
    fi
    sudo cp "$NGINX_CONF" /etc/nginx/sites-available/air-quality-monitoring
    sudo rm -f /etc/nginx/sites-enabled/default
    sudo ln -sf /etc/nginx/sites-available/air-quality-monitoring /etc/nginx/sites-enabled/
    if sudo nginx -t; then
        log_info "✓ Nginx configuration is valid"
        sudo systemctl reload nginx 2>/dev/null || sudo service nginx reload
        log_info "✓ Nginx configuration applied"
    else
        log_error "✗ Nginx configuration test failed"
        exit 1
    fi
}

start_gunicorn() {
    log_step "Starting application with Gunicorn..."
    cd "$PROJECT_DIR"
    pkill -f "gunicorn.*wsgi:app" || true
    sleep 2
    source "$VENV_PATH/bin/activate"
    nohup gunicorn \
        --config gunicorn.conf.py \
        --bind 127.0.0.1:8000 \
        --workers 2 \
        --timeout 30 \
        --log-level info \
        --access-logfile logs/access.log \
        --error-logfile logs/error.log \
        --daemon \
        --pid logs/gunicorn.pid \
        wsgi:app
    sleep 3
    if pgrep -f "gunicorn.*wsgi:app" > /dev/null; then
        log_info "✓ Gunicorn started successfully"
        return 0
    else
        log_error "✗ Failed to start Gunicorn"
        return 1
    fi
}

stop_gunicorn() {
    log_step "Stopping Gunicorn..."
    if [ -f "$PROJECT_DIR/logs/gunicorn.pid" ]; then
        local pid=$(cat "$PROJECT_DIR/logs/gunicorn.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid"
            sleep 2
            if kill -0 "$pid" 2>/dev/null; then
                kill -KILL "$pid"
            fi
            rm -f "$PROJECT_DIR/logs/gunicorn.pid"
        fi
    fi
    pkill -f "gunicorn.*wsgi:app" || true
    log_info "✓ Gunicorn stopped"
}

check_status() {
    log_step "Checking application status..."
    if pgrep -f "gunicorn.*wsgi:app" > /dev/null; then
        log_info "✓ Gunicorn is running"
        local pid=$(pgrep -f "gunicorn.*wsgi:app" | head -1)
        echo "  PID: $pid"
        if command -v wget &> /dev/null; then
            if wget -qO- http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
                log_info "✓ Application is responding"
                echo "  Health check: http://127.0.0.1:8000/api/health"
            else
                log_warn "✗ Application is not responding"
            fi
        fi
    else
        log_warn "✗ Gunicorn is not running"
    fi
    if command -v nginx &> /dev/null; then
        if systemctl is-active --quiet nginx; then
            log_info "✓ Nginx is running"
            if command -v wget &> /dev/null; then
                if wget -qO- http://localhost/api/health > /dev/null 2>&1; then
                    log_info "✓ Nginx proxy is working"
                    echo "  Frontend URL: http://localhost"
                else
                    log_warn "✗ Nginx proxy test failed"
                fi
            fi
        else
            log_warn "✗ Nginx is not running"
        fi
    else
        log_warn "Nginx is not installed"
    fi
}

view_logs() {
    log_step "Recent application logs:"
    echo -e "\n${BLUE}=== Gunicorn Error Log ===${NC}"
    tail -20 "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "No error log found"
    echo -e "\n${BLUE}=== Gunicorn Access Log ===${NC}"
    tail -10 "$PROJECT_DIR/logs/access.log" 2>/dev/null || echo "No access log found"
    if command -v nginx &> /dev/null; then
        echo -e "\n${BLUE}=== Nginx Error Log ===${NC}"
        sudo tail -10 "$PROJECT_DIR/logs/nginx_error.log" 2>/dev/null || echo "No nginx error log found"
    fi
}

deploy() {
    log_header "🚀 Starting Air Quality Monitoring System Deployment"
    check_prerequisites
    setup_directories
    test_application
    stop_gunicorn
    start_gunicorn
    if command -v nginx &> /dev/null; then
        setup_nginx
    else
        log_warn "Nginx not installed - skipping reverse proxy setup"
        log_info "Application available at: http://127.0.0.1:8000"
    fi
    sleep 2
    check_status
    log_header "✅ Deployment completed successfully!"
    echo ""
    echo "Application URLs:"
    echo "  Direct: http://127.0.0.1:8000"
    if command -v nginx &> /dev/null; then
        echo "  Nginx:  http://localhost"
    fi
    echo ""
    echo "Management commands:"
    echo "  $0 status  - Check status"
    echo "  $0 logs    - View logs"
    echo "  $0 stop    - Stop application"
    echo "  $0 restart - Restart application"
}

usage() {
    echo "Air Quality Monitoring System - Deployment Manager"
    echo ""
    echo "Usage: $0 [deploy|start|stop|restart|status|logs|test]"
}

case "${1:-}" in
    deploy)
        deploy
        ;;
    start)
        check_prerequisites && start_gunicorn
        ;;
    stop)
        stop_gunicorn
        ;;
    restart)
        check_prerequisites && stop_gunicorn && sleep 2 && start_gunicorn
        ;;
    status)
        check_status
        ;;
    logs)
        view_logs
        ;;
    test)
        test_application
        ;;
    *)
        usage
        exit 1
        ;;
esac
