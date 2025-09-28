#!/bin/bash

################################################################################
# Air Quality Monitoring System - Health Check & Auto-Fix Script
# Automatically detects and fixes common deployment issues
################################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_USER=$(whoami)

log() { echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"; }
log_error() { echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"; }
log_info() { echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO:${NC} $1"; }

header() {
    echo -e "\n${PURPLE}================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}================================${NC}\n"
}

# Fix permissions
fix_permissions() {
    header "FIXING PERMISSIONS"
    
    cd "$PROJECT_DIR"
    
    # Fix ownership
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
    
    # Fix directory permissions
    find "$PROJECT_DIR" -type d -exec chmod 755 {} \;
    
    # Fix file permissions
    find "$PROJECT_DIR" -type f -name "*.sh" -exec chmod +x {} \;
    find "$PROJECT_DIR" -type f -name "*.py" -exec chmod 644 {} \;
    
    # Fix log directory
    mkdir -p logs
    chmod 755 logs
    
    log "Permissions fixed"
}

# Fix Python environment
fix_python_environment() {
    header "CHECKING PYTHON ENVIRONMENT"
    
    cd "$PROJECT_DIR"
    
    # Check if virtual environment exists
    if [ ! -d "venv" ]; then
        log "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate and check dependencies
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip wheel setuptools
    
    # Install/update requirements
    if [ -f "requirements.txt" ]; then
        log "Installing/updating Python dependencies..."
        pip install -r requirements.txt
    else
        log_error "requirements.txt not found!"
        return 1
    fi
    
    # Test Flask app
    log "Testing Flask application..."
    timeout 30 python3 -c "
try:
    from backend.app import create_app
    app = create_app()
    print('✓ Flask app test passed')
except Exception as e:
    print(f'✗ Flask app test failed: {e}')
    exit(1)
"
    
    log "Python environment verified"
}

# Fix database connection
fix_database() {
    header "CHECKING DATABASE CONNECTION"
    
    # Ensure MongoDB is running
    if ! sudo systemctl is-active --quiet mongod; then
        log "Starting MongoDB..."
        sudo systemctl start mongod
        sleep 5
    fi
    
    # Test connection
    if command -v mongosh > /dev/null; then
        MONGO_CMD="mongosh --quiet"
    elif command -v mongo > /dev/null; then
        MONGO_CMD="mongo --quiet"
    else
        log_error "MongoDB client not found"
        return 1
    fi
    
    if $MONGO_CMD --eval "db.runCommand('ping')" > /dev/null 2>&1; then
        log "✓ MongoDB connection successful"
    else
        log_error "✗ MongoDB connection failed"
        return 1
    fi
}

# Fix nginx configuration
fix_nginx() {
    header "CHECKING NGINX CONFIGURATION"
    
    # Test nginx config
    if ! sudo nginx -t; then
        log_error "Nginx configuration error"
        return 1
    fi
    
    # Ensure our site is enabled
    if [ ! -L "/etc/nginx/sites-enabled/air-quality-monitoring" ]; then
        log "Enabling air-quality-monitoring site..."
        sudo ln -sf /etc/nginx/sites-available/air-quality-monitoring /etc/nginx/sites-enabled/
    fi
    
    # Remove default site if it exists
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Restart nginx
    sudo systemctl restart nginx
    
    if sudo systemctl is-active --quiet nginx; then
        log "✓ Nginx is running correctly"
    else
        log_error "✗ Nginx failed to start"
        return 1
    fi
}

# Fix systemd service
fix_systemd_service() {
    header "CHECKING SYSTEMD SERVICE"
    
    # Reload systemd daemon
    sudo systemctl daemon-reload
    
    # Check if service file exists
    if [ ! -f "/etc/systemd/system/air-quality-monitoring.service" ]; then
        log_error "Service file not found. Please run the deployment script first."
        return 1
    fi
    
    # Enable and start service
    sudo systemctl enable air-quality-monitoring.service
    sudo systemctl restart air-quality-monitoring.service
    
    # Wait and check status
    sleep 10
    
    if sudo systemctl is-active --quiet air-quality-monitoring.service; then
        log "✓ Air Quality Monitoring service is running"
    else
        log_error "✗ Service failed to start"
        sudo systemctl status air-quality-monitoring.service --no-pager -l
        return 1
    fi
}

# Fix firewall
fix_firewall() {
    header "CHECKING FIREWALL CONFIGURATION"
    
    # Enable UFW if not active
    if ! sudo ufw status | grep -q "Status: active"; then
        log "Enabling UFW firewall..."
        sudo ufw --force enable
    fi
    
    # Allow necessary ports
    sudo ufw allow ssh
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    
    # Allow MongoDB locally
    sudo ufw allow from 127.0.0.1 to any port 27017
    
    sudo ufw reload
    
    log "✓ Firewall configured"
}

# Test all endpoints
test_endpoints() {
    header "TESTING ALL ENDPOINTS"
    
    # Wait for services to be fully ready
    sleep 5
    
    local failed=0
    
    # Test direct Gunicorn
    log_info "Testing Gunicorn (port 8000)..."
    if timeout 10 curl -sf http://127.0.0.1:8000/api/health > /dev/null; then
        log "✓ Gunicorn responding"
    else
        log_error "✗ Gunicorn not responding"
        failed=1
    fi
    
    # Test Nginx proxy
    log_info "Testing Nginx proxy..."
    if timeout 10 curl -sf http://localhost/api/health > /dev/null; then
        log "✓ Nginx proxy working"
    else
        log_error "✗ Nginx proxy not working"
        failed=1
    fi
    
    # Test main page
    log_info "Testing main page..."
    if timeout 10 curl -sf http://localhost/ > /dev/null; then
        log "✓ Main page accessible"
    else
        log_error "✗ Main page not accessible"
        failed=1
    fi
    
    # Test API endpoints
    log_info "Testing API endpoints..."
    if timeout 10 curl -sf http://localhost/api/stations > /dev/null; then
        log "✓ API endpoints working"
    else
        log_warn "⚠ Some API endpoints may not be working (this might be normal if no data is available)"
    fi
    
    # Test external access
    log_info "Testing external access..."
    PUBLIC_IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ]; then
        if timeout 15 curl -sf "http://$PUBLIC_IP/api/health" > /dev/null; then
            log "✓ External access working from $PUBLIC_IP"
        else
            log_warn "⚠ External access may be blocked by cloud firewall (this is common)"
            log_info "You may need to open port 80 in your cloud provider's security groups"
        fi
    else
        log_warn "Could not determine public IP address"
    fi
    
    return $failed
}

# Generate system report
generate_report() {
    header "SYSTEM HEALTH REPORT"
    
    echo "=== Services Status ==="
    echo -n "MongoDB: "
    if sudo systemctl is-active --quiet mongod; then
        echo "✓ RUNNING"
    else
        echo "✗ STOPPED"
    fi
    
    echo -n "Nginx: "
    if sudo systemctl is-active --quiet nginx; then
        echo "✓ RUNNING"
    else
        echo "✗ STOPPED"
    fi
    
    echo -n "Air Quality App: "
    if sudo systemctl is-active --quiet air-quality-monitoring.service; then
        echo "✓ RUNNING"
    else
        echo "✗ STOPPED"
    fi
    
    echo -e "\n=== Port Status ==="
    ss -tlnp | grep -E ':(80|8000|27017)\b' | while read line; do
        if echo "$line" | grep -q ":80 "; then
            echo "✓ HTTP (80): LISTENING"
        elif echo "$line" | grep -q ":8000 "; then
            echo "✓ Gunicorn (8000): LISTENING"
        elif echo "$line" | grep -q ":27017 "; then
            echo "✓ MongoDB (27017): LISTENING"
        fi
    done
    
    echo -e "\n=== System Resources ==="
    echo "Memory: $(free -h | awk 'NR==2{printf "Used: %s, Available: %s", $3, $7}')"
    echo "Disk: $(df -h "$PROJECT_DIR" | awk 'NR==2{printf "Used: %s, Available: %s", $3, $4}')"
    
    echo -e "\n=== Recent Errors ==="
    if [ -f "$PROJECT_DIR/logs/error.log" ]; then
        echo "Application errors (last 5):"
        tail -5 "$PROJECT_DIR/logs/error.log" 2>/dev/null || echo "No errors in application log"
    else
        echo "No error log file found"
    fi
    
    echo -e "\n=== Access URLs ==="
    echo "• Local: http://localhost"
    echo "• Direct: http://127.0.0.1:8000"
    
    PUBLIC_IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ]; then
        echo "• Public: http://$PUBLIC_IP"
    fi
    
    echo -e "\n=== Management Commands ==="
    echo "• Check this report: $0"
    echo "• View logs: ./logs.sh"
    echo "• Restart services: ./restart.sh"
    echo "• Check status: ./status.sh"
}

# Auto-fix function
auto_fix() {
    header "STARTING AUTO-FIX PROCESS"
    
    local errors=0
    
    fix_permissions || ((errors++))
    fix_python_environment || ((errors++))
    fix_database || ((errors++))
    fix_nginx || ((errors++))
    fix_systemd_service || ((errors++))
    fix_firewall || ((errors++))
    
    if [ $errors -eq 0 ]; then
        log "✅ All auto-fixes completed successfully"
    else
        log_warn "⚠️ Some issues could not be auto-fixed ($errors errors)"
    fi
    
    return $errors
}

# Main function
main() {
    echo -e "${PURPLE}"
    echo "################################################################################"
    echo "#           Air Quality Monitoring System - Health Check & Auto-Fix           #"
    echo "################################################################################"
    echo -e "${NC}\n"
    
    case "${1:-check}" in
        "check")
            generate_report
            test_endpoints
            ;;
        "fix")
            auto_fix
            echo -e "\n"
            generate_report
            echo -e "\n"
            test_endpoints
            ;;
        "test")
            test_endpoints
            ;;
        *)
            echo "Usage: $0 [check|fix|test]"
            echo "  check - Generate health report and test endpoints"
            echo "  fix   - Auto-fix common issues and test"
            echo "  test  - Test all endpoints only"
            exit 1
            ;;
    esac
}

main "$@"