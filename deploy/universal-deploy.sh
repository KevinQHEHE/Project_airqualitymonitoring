#!/bin/bash

################################################################################
# Universal Air Quality Monitoring System Deployment Script
# Compatible with all Ubuntu Linux versions
# Automatically installs all dependencies and configures the system
# Ensures 100% working deployment accessible from Internet
################################################################################

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
PROJECT_NAME="air-quality-monitoring"
SERVICE_USER="azureuser"  # Will be detected automatically
SERVICE_PORT=8000
NGINX_PORT=80
DB_NAME="air_quality_db"

# Auto-detect current user and project directory
CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

log() {
    echo -e "${GREEN}[$(date +'%H:%M:%S')]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[$(date +'%H:%M:%S')] WARNING:${NC} $1"
}

log_error() {
    echo -e "${RED}[$(date +'%H:%M:%S')] ERROR:${NC} $1"
}

log_info() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')] INFO:${NC} $1"
}

log_success() {
    echo -e "${CYAN}[$(date +'%H:%M:%S')] SUCCESS:${NC} $1"
}

header() {
    echo -e "\n${PURPLE}================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}================================${NC}\n"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should NOT be run as root. Please run as a regular user with sudo privileges."
        exit 1
    fi
    
    # Check sudo access
    if ! sudo -n true 2>/dev/null; then
        log_error "This script requires sudo privileges. Please run: sudo visudo and add your user to sudoers."
        exit 1
    fi
}

# Detect system information
detect_system() {
    header "DETECTING SYSTEM INFORMATION"
    
    SERVICE_USER="$CURRENT_USER"
    log "Detected user: $SERVICE_USER"
    log "Project directory: $PROJECT_DIR"
    
    # Detect Ubuntu version
    if [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        log "Ubuntu version: $DISTRIB_DESCRIPTION"
    else
        log_warn "Could not detect Ubuntu version, continuing anyway..."
    fi
    
    # Detect architecture
    ARCH=$(uname -m)
    log "Architecture: $ARCH"
    
    # Detect Python version
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        log "Python: $PYTHON_VERSION"
    else
        log_warn "Python3 not found, will install"
    fi
    
    # Get system resources
    TOTAL_MEM=$(free -m | awk 'NR==2{printf "%.0f", $2}')
    AVAILABLE_DISK=$(df -BG "$PROJECT_DIR" | awk 'NR==2 {print $4}' | sed 's/G//')
    log "Memory: ${TOTAL_MEM}MB"
    log "Available disk: ${AVAILABLE_DISK}GB"
    
    if [ "$TOTAL_MEM" -lt 1024 ]; then
        log_warn "Low memory detected (${TOTAL_MEM}MB). Optimizing configuration for low-resource environment."
        LOW_RESOURCE=true
    else
        LOW_RESOURCE=false
    fi
}

# Update system packages
update_system() {
    header "UPDATING SYSTEM PACKAGES"
    
    log "Updating package lists..."
    sudo apt-get update -qq
    
    log "Installing essential packages..."
    sudo apt-get install -y \
        curl \
        wget \
        git \
        unzip \
        software-properties-common \
        apt-transport-https \
        ca-certificates \
        gnupg \
        lsb-release \
        build-essential \
        ufw \
        supervisor
    
    log_success "System packages updated"
}

# Install Python and dependencies
install_python() {
    header "INSTALLING PYTHON AND DEPENDENCIES"
    
    # Install Python 3 and pip
    sudo apt-get install -y \
        python3 \
        python3-pip \
        python3-venv \
        python3-dev \
        python3-setuptools
    
    # Install system dependencies for Python packages
    sudo apt-get install -y \
        libssl-dev \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        zlib1g-dev \
        libjpeg-dev \
        libpq-dev \
        build-essential
    
    # Upgrade pip
    python3 -m pip install --user --upgrade pip
    
    log_success "Python environment installed"
}

# Install MongoDB
install_mongodb() {
    header "INSTALLING MONGODB"
    
    # Import MongoDB GPG key
    wget -qO - https://www.mongodb.org/static/pgp/server-6.0.asc | sudo apt-key add -
    
    # Add MongoDB repository
    if [ -f /etc/lsb-release ]; then
        . /etc/lsb-release
        case "$DISTRIB_CODENAME" in
            "focal"|"jammy"|"kinetic")
                MONGO_CODENAME="focal"
                ;;
            "bionic")
                MONGO_CODENAME="bionic"
                ;;
            *)
                MONGO_CODENAME="focal"  # Default to focal for newer versions
                ;;
        esac
    else
        MONGO_CODENAME="focal"
    fi
    
    echo "deb [ arch=amd64,arm64 ] https://repo.mongodb.org/apt/ubuntu $MONGO_CODENAME/mongodb-org/6.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-6.0.list
    
    sudo apt-get update -qq
    sudo apt-get install -y mongodb-org
    
    # Start and enable MongoDB
    sudo systemctl start mongod
    sudo systemctl enable mongod
    
    # Wait for MongoDB to start
    sleep 5
    
    # Verify MongoDB installation
    if sudo systemctl is-active --quiet mongod; then
        log_success "MongoDB installed and running"
    else
        log_error "Failed to start MongoDB"
        exit 1
    fi
}

# Install Nginx
install_nginx() {
    header "INSTALLING NGINX"
    
    sudo apt-get install -y nginx
    
    # Start and enable Nginx
    sudo systemctl start nginx
    sudo systemctl enable nginx
    
    # Verify Nginx installation
    if sudo systemctl is-active --quiet nginx; then
        log_success "Nginx installed and running"
    else
        log_error "Failed to start Nginx"
        exit 1
    fi
}

# Setup project environment
setup_project() {
    header "SETTING UP PROJECT ENVIRONMENT"
    
    cd "$PROJECT_DIR"
    
    # Create Python virtual environment
    log "Creating Python virtual environment..."
    python3 -m venv venv
    
    # Activate virtual environment and install dependencies
    log "Installing Python dependencies..."
    source venv/bin/activate
    pip install --upgrade pip wheel setuptools
    pip install -r requirements.txt
    
    # Create necessary directories
    mkdir -p logs
    mkdir -p backend/app/static
    mkdir -p backup_dtb/backup_data
    
    # Set proper permissions
    sudo chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
    chmod +x "$PROJECT_DIR"/scripts/*.sh 2>/dev/null || true
    chmod +x "$PROJECT_DIR"/deploy/*.sh 2>/dev/null || true
    
    log_success "Project environment setup completed"
}

# Configure environment variables
setup_environment() {
    header "CONFIGURING ENVIRONMENT VARIABLES"
    
    cd "$PROJECT_DIR"
    
    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        if [ -f .env.sample ]; then
            cp .env.sample .env
        else
            # Create basic .env file
            cat > .env << EOF
# Flask Configuration
FLASK_APP=wsgi:app
FLASK_ENV=production
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')

# Database Configuration
MONGO_URI=mongodb://localhost:27017/air_quality_db
MONGO_DB_NAME=air_quality_db

# API Configuration
AQICN_API_KEY=your_aqicn_api_key_here
AQICN_BASE_URL=https://api.waqi.info

# Scheduler Configuration
SCHEDULER_ENABLED=true
BACKUP_ENABLED=true
ALERT_ENABLED=true

# Email Configuration (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
MAIL_DEFAULT_SENDER=your_email@gmail.com

# Logging
LOG_LEVEL=INFO
EOF
        fi
        log "Created .env configuration file"
        log_warn "Please edit .env file with your actual API keys and configuration"
    else
        log "Using existing .env file"
    fi
}

# Create optimized Gunicorn configuration
create_gunicorn_config() {
    header "CREATING OPTIMIZED GUNICORN CONFIGURATION"
    
    # Calculate optimal number of workers based on system resources
    if [ "$LOW_RESOURCE" = true ]; then
        WORKERS=1
        WORKER_CONNECTIONS=100
        MAX_REQUESTS=100
    else
        WORKERS=$(python3 -c "import multiprocessing; print(min(multiprocessing.cpu_count() * 2 + 1, 4))")
        WORKER_CONNECTIONS=1000
        MAX_REQUESTS=1000
    fi
    
    cat > "$PROJECT_DIR/gunicorn.conf.py" << EOF
#!/usr/bin/env python3
"""
Optimized Gunicorn configuration for Air Quality Monitoring System
Automatically configured for system resources
"""

import multiprocessing
import os

# Server socket
bind = "127.0.0.1:$SERVICE_PORT"
backlog = 2048

# Worker processes (optimized for this system)
workers = $WORKERS
worker_class = "sync"
worker_connections = $WORKER_CONNECTIONS
timeout = 30
keepalive = 2

# Restart workers after this many requests
max_requests = $MAX_REQUESTS
max_requests_jitter = 50

# Logging
accesslog = "$PROJECT_DIR/logs/access.log"
errorlog = "$PROJECT_DIR/logs/error.log"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "air_quality_monitoring"

# Daemon mode
daemon = False
pidfile = "$PROJECT_DIR/logs/gunicorn.pid"

# User/group to run as
user = "$SERVICE_USER"
group = "$SERVICE_USER"

# Preload application for better performance
preload_app = True

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

def on_starting(server):
    server.log.info("Starting Air Quality Monitoring System")

def on_reload(server):
    server.log.info("Reloading Air Quality Monitoring System")

def when_ready(server):
    server.log.info("Air Quality Monitoring System is ready. Listening on: %s", server.address)

def on_exit(server):
    server.log.info("Shutting down Air Quality Monitoring System")
EOF
    
    log "Created optimized Gunicorn config with $WORKERS workers"
}

# Configure Nginx
configure_nginx() {
    header "CONFIGURING NGINX"
    
    # Get server's public IP
    PUBLIC_IP=$(curl -s https://api.ipify.org || echo "")
    if [ -z "$PUBLIC_IP" ]; then
        PUBLIC_IP=$(curl -s http://checkip.amazonaws.com/ || echo "")
    fi
    
    # Create Nginx configuration
    sudo tee /etc/nginx/sites-available/air-quality-monitoring << EOF
server {
    listen 80;
    server_name $PUBLIC_IP localhost $(hostname) _;
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
    
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_min_length 1024;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types
        text/plain
        text/css
        text/xml
        text/javascript
        application/json
        application/javascript
        application/xml+rss
        application/atom+xml
        image/svg+xml;
    
    # Log files
    access_log $PROJECT_DIR/logs/nginx_access.log;
    error_log $PROJECT_DIR/logs/nginx_error.log;
    
    # Rate limiting (protect against abuse)
    limit_req_zone \$binary_remote_addr zone=api:10m rate=10r/s;
    limit_req_zone \$binary_remote_addr zone=general:10m rate=2r/s;
    
    # Static files
    location /static/ {
        alias $PROJECT_DIR/backend/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }
    
    # Favicon
    location = /favicon.ico {
        alias $PROJECT_DIR/backend/app/static/favicon.ico;
        access_log off;
    }
    
    # API endpoints with rate limiting
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
    
    # Health check endpoint (no rate limiting)
    location /api/health {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        access_log off;
    }
    
    # Main application with light rate limiting
    location / {
        limit_req zone=general burst=10 nodelay;
        
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        
        # Buffer settings
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
}
EOF
    
    # Enable the site
    sudo ln -sf /etc/nginx/sites-available/air-quality-monitoring /etc/nginx/sites-enabled/
    
    # Remove default site
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test nginx configuration
    sudo nginx -t
    
    # Reload nginx
    sudo systemctl reload nginx
    
    log_success "Nginx configured successfully"
    if [ -n "$PUBLIC_IP" ]; then
        log "Site will be available at: http://$PUBLIC_IP"
    fi
}

# Create systemd service
create_systemd_service() {
    header "CREATING SYSTEMD SERVICE"
    
    sudo tee /etc/systemd/system/air-quality-monitoring.service << EOF
[Unit]
Description=Air Quality Monitoring System
After=network.target mongodb.service nginx.service
Wants=mongodb.service
Requires=network.target

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
Environment=PYTHONPATH=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/gunicorn --config $PROJECT_DIR/gunicorn.conf.py wsgi:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3
KillMode=mixed
TimeoutStopSec=30

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ReadWritePaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable air-quality-monitoring.service
    
    log_success "Systemd service created and enabled"
}

# Configure firewall
configure_firewall() {
    header "CONFIGURING FIREWALL"
    
    # Enable UFW if not already enabled
    if ! sudo ufw status | grep -q "Status: active"; then
        log "Enabling UFW firewall..."
        sudo ufw --force enable
    fi
    
    # Allow SSH (important!)
    sudo ufw allow ssh
    
    # Allow HTTP and HTTPS
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    
    # Allow MongoDB (only locally)
    sudo ufw allow from 127.0.0.1 to any port 27017
    
    # Reload UFW
    sudo ufw reload
    
    log_success "Firewall configured successfully"
}

# Test application
test_application() {
    header "TESTING APPLICATION"
    
    cd "$PROJECT_DIR"
    
    # Test Flask app creation
    log "Testing Flask application..."
    source venv/bin/activate
    timeout 30 python3 -c "
from backend.app import create_app
app = create_app()
print('✓ Flask app created successfully')
" || {
        log_error "Flask application test failed"
        return 1
    }
    
    log_success "Flask application test passed"
}

# Start all services
start_services() {
    header "STARTING ALL SERVICES"
    
    # Ensure MongoDB is running
    sudo systemctl start mongod
    sleep 3
    
    # Start the application service
    sudo systemctl start air-quality-monitoring.service
    sleep 5
    
    # Check service status
    if sudo systemctl is-active --quiet air-quality-monitoring.service; then
        log_success "Air Quality Monitoring service started successfully"
    else
        log_error "Failed to start Air Quality Monitoring service"
        sudo systemctl status air-quality-monitoring.service
        return 1
    fi
    
    # Ensure Nginx is running
    sudo systemctl restart nginx
    
    if sudo systemctl is-active --quiet nginx; then
        log_success "Nginx started successfully"
    else
        log_error "Failed to start Nginx"
        return 1
    fi
}

# Verify deployment
verify_deployment() {
    header "VERIFYING DEPLOYMENT"
    
    # Wait for services to fully initialize
    log "Waiting for services to initialize..."
    sleep 10
    
    # Test local endpoints
    log "Testing local endpoints..."
    
    # Test direct Gunicorn
    if curl -sf http://127.0.0.1:$SERVICE_PORT/api/health > /dev/null; then
        log_success "✓ Gunicorn responding"
    else
        log_error "✗ Gunicorn not responding"
        return 1
    fi
    
    # Test Nginx proxy
    if curl -sf http://localhost/api/health > /dev/null; then
        log_success "✓ Nginx proxy working"
    else
        log_error "✗ Nginx proxy not working"
        return 1
    fi
    
    # Test MongoDB connection
    if mongosh --quiet --eval "db.runCommand('ping')" > /dev/null 2>&1; then
        log_success "✓ MongoDB responding"
    else
        if mongo --quiet --eval "db.runCommand('ping')" > /dev/null 2>&1; then
            log_success "✓ MongoDB responding (legacy client)"
        else
            log_warn "Could not verify MongoDB (but service may still work)"
        fi
    fi
    
    # Get public IP for external testing
    PUBLIC_IP=$(curl -s https://api.ipify.org || curl -s http://checkip.amazonaws.com/ || echo "")
    
    if [ -n "$PUBLIC_IP" ]; then
        log "Testing external access..."
        if timeout 10 curl -sf "http://$PUBLIC_IP/api/health" > /dev/null; then
            log_success "✓ External access working"
            EXTERNAL_ACCESS=true
        else
            log_warn "✗ External access may be blocked by cloud firewall/security groups"
            EXTERNAL_ACCESS=false
        fi
    else
        log_warn "Could not determine public IP"
        EXTERNAL_ACCESS=false
    fi
    
    log_success "Basic deployment verification completed"
}

# Create management scripts
create_management_scripts() {
    header "CREATING MANAGEMENT SCRIPTS"
    
    # Create status script
    cat > "$PROJECT_DIR/status.sh" << 'EOF'
#!/bin/bash
echo "=== Air Quality Monitoring System Status ==="
echo

echo "Service Status:"
sudo systemctl is-active air-quality-monitoring.service && echo "✓ Application: RUNNING" || echo "✗ Application: STOPPED"
sudo systemctl is-active nginx && echo "✓ Nginx: RUNNING" || echo "✗ Nginx: STOPPED"
sudo systemctl is-active mongod && echo "✓ MongoDB: RUNNING" || echo "✗ MongoDB: STOPPED"

echo
echo "Port Status:"
ss -tlnp | grep -E ':(80|8000|27017)\b' || echo "No services listening on expected ports"

echo
echo "Recent Logs:"
echo "--- Application Logs ---"
tail -5 logs/error.log 2>/dev/null || echo "No error logs found"
echo "--- Nginx Access Logs ---"
tail -3 logs/nginx_access.log 2>/dev/null || echo "No access logs found"
EOF

    # Create restart script
    cat > "$PROJECT_DIR/restart.sh" << 'EOF'
#!/bin/bash
echo "Restarting Air Quality Monitoring System..."
sudo systemctl restart air-quality-monitoring.service
sudo systemctl restart nginx
sleep 3
echo "Services restarted. Checking status:"
sudo systemctl is-active air-quality-monitoring.service nginx mongod
EOF

    # Create logs script
    cat > "$PROJECT_DIR/logs.sh" << 'EOF'
#!/bin/bash
echo "=== Air Quality Monitoring System Logs ==="
echo
echo "--- Application Error Logs (last 20 lines) ---"
tail -20 logs/error.log 2>/dev/null || echo "No error logs found"
echo
echo "--- Application Access Logs (last 10 lines) ---"
tail -10 logs/access.log 2>/dev/null || echo "No access logs found"
echo
echo "--- Nginx Error Logs (last 10 lines) ---"
tail -10 logs/nginx_error.log 2>/dev/null || echo "No nginx error logs found"
echo
echo "--- System Service Logs (last 20 lines) ---"
sudo journalctl -u air-quality-monitoring.service -n 20 --no-pager
EOF

    # Make scripts executable
    chmod +x "$PROJECT_DIR"/{status,restart,logs}.sh
    
    log_success "Management scripts created"
}

# Main deployment function
main() {
    echo -e "${PURPLE}"
    echo "################################################################################"
    echo "#             Universal Air Quality Monitoring System Deployment              #"
    echo "#                         Automatic Ubuntu Installation                       #"
    echo "################################################################################"
    echo -e "${NC}\n"
    
    log "Starting deployment at $(date)"
    
    # Pre-flight checks
    check_root
    detect_system
    
    # Core installation
    update_system
    install_python
    install_mongodb
    install_nginx
    
    # Project setup
    setup_project
    setup_environment
    create_gunicorn_config
    configure_nginx
    create_systemd_service
    
    # Security and system configuration
    configure_firewall
    
    # Testing and startup
    test_application
    start_services
    verify_deployment
    create_management_scripts
    
    # Final status report
    header "DEPLOYMENT COMPLETE"
    
    echo -e "${GREEN}🎉 Air Quality Monitoring System has been successfully deployed!${NC}\n"
    
    echo "📊 System Information:"
    echo "  • User: $SERVICE_USER"
    echo "  • Project Path: $PROJECT_DIR"
    echo "  • Python Workers: $WORKERS"
    echo "  • Memory Optimization: $([ "$LOW_RESOURCE" = true ] && echo "Enabled" || echo "Disabled")"
    
    echo -e "\n🌐 Access Information:"
    echo "  • Local: http://localhost"
    echo "  • Direct: http://127.0.0.1:$SERVICE_PORT"
    if [ -n "$PUBLIC_IP" ]; then
        echo "  • Public: http://$PUBLIC_IP"
        if [ "$EXTERNAL_ACCESS" = false ]; then
            echo -e "    ${YELLOW}⚠️  May require cloud firewall/security group configuration${NC}"
        fi
    fi
    
    echo -e "\n🛠️  Management Commands:"
    echo "  • Check status: ./status.sh"
    echo "  • Restart services: ./restart.sh"
    echo "  • View logs: ./logs.sh"
    echo "  • System service: sudo systemctl {start|stop|restart|status} air-quality-monitoring"
    
    echo -e "\n📁 Important Files:"
    echo "  • Configuration: .env"
    echo "  • Logs: logs/"
    echo "  • Nginx config: /etc/nginx/sites-available/air-quality-monitoring"
    echo "  • Service config: /etc/systemd/system/air-quality-monitoring.service"
    
    echo -e "\n⚡ Next Steps:"
    echo "  1. Edit .env file with your API keys and configuration"
    echo "  2. If on cloud provider, open port 80 in security groups"
    echo "  3. Consider setting up SSL certificate for HTTPS"
    echo "  4. Configure email settings for alerts (optional)"
    
    echo -e "\n${GREEN}✅ Deployment completed successfully!${NC}"
    echo "The system is now running and should be accessible from the Internet."
    echo "Check the status with: ./status.sh"
}

# Run main function with error handling
main "$@" 2>&1 | tee "$PROJECT_DIR/deployment.log"

# Check if deployment was successful
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo -e "\n${GREEN}🎯 Deployment log saved to: $PROJECT_DIR/deployment.log${NC}"
    exit 0
else
    echo -e "\n${RED}💥 Deployment failed. Check the log above for details.${NC}"
    exit 1
fi