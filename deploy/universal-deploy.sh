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

SKIP_GIT_UPDATE=false
SKIP_TESTS=false
CERT_OBTAINED=false

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


usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --skip-git      Skip pulling the latest Git changes (keep current working tree)
  --skip-tests    Skip the Flask smoke test step
  -h, --help      Show this help message
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --skip-git)
                SKIP_GIT_UPDATE=true
                ;;
            --skip-tests)
                SKIP_TESTS=true
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_warn "Unknown option: $1"
                ;;
        esac
        shift
    done
}

# Configuration
PROJECT_NAME="air-quality-monitoring"
# Load per-server overrides from deploy/env (copy deploy/env.sample -> deploy/env and edit)
if [ -f "$(dirname "${BASH_SOURCE[0]}")/env" ]; then
    # shellcheck source=/dev/null
    source "$(dirname "${BASH_SOURCE[0]}")/env"
    log_info "Loaded deploy/env overrides"
else
    SERVICE_USER="azureuser"  # Will be detected automatically
    SERVICE_PORT=8000
    NGINX_PORT=80
    DB_NAME="air_quality_db"
fi

# Auto-detect current user and project directory
CURRENT_USER=$(whoami)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# If deploy/env provided a MONGO_URI that is not localhost, do not attempt to install MongoDB locally
if [ -n "${MONGO_URI:-}" ]; then
    case "$MONGO_URI" in
        *localhost*|*127.0.0.1*|mongodb://localhost*|mongodb://127.0.0.1*)
            # local DB - keep default behaviour
            ;;
        *)
            INSTALL_MONGODB=false
            log_info "MONGO_URI points to remote host; skipping local MongoDB installation"
            ;;
    esac
fi

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

update_repository() {
    header "UPDATING APPLICATION SOURCE"

    if [ "$SKIP_GIT_UPDATE" = true ]; then
        log_info "Skipping git update (--skip-git flag set)"
        return
    fi

    cd "$PROJECT_DIR"

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_info "$PROJECT_DIR is not a Git repository; skipping git operations"
        return
    fi

    local remote=${GIT_REMOTE:-origin}
    local current_branch
    current_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
    local target_branch=${GIT_BRANCH:-$current_branch}
    if [ -z "$target_branch" ] || [ "$target_branch" = "HEAD" ]; then
        target_branch=main
    fi

    if git status --porcelain --untracked-files=no | grep -q .; then
        log_warn "Local changes detected; skipping git pull to avoid overwriting work"
        return
    fi

    log "Fetching $remote..."
    if ! git fetch "$remote"; then
        log_warn "Failed to fetch from $remote; continuing with existing sources"
        return
    fi

    if ! git show-ref --verify --quiet "refs/heads/$target_branch"; then
        if git show-ref --verify --quiet "refs/remotes/$remote/$target_branch"; then
            log "Creating local branch $target_branch from $remote/$target_branch"
            if ! git checkout -b "$target_branch" "$remote/$target_branch"; then
                log_warn "Unable to checkout branch $target_branch; staying on $(git rev-parse --abbrev-ref HEAD)"
            fi
        fi
    fi

    log "Switching to branch $target_branch"
    if ! git checkout "$target_branch"; then
        log_warn "Could not checkout branch $target_branch; keeping $(git rev-parse --abbrev-ref HEAD)"
    fi

    log "Pulling latest changes..."
    if git pull --ff-only "$remote" "$target_branch"; then
        log_success "Repository updated to latest $target_branch"
    else
        log_warn "git pull failed (non-fast-forward). Resolve conflicts manually before rerunning."
    fi

    if [ -f .gitmodules ]; then
        log "Updating git submodules..."
        git submodule update --init --recursive || log_warn "Failed to update submodules"
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
        supervisor \
        acl \
    
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
    if [ "${INSTALL_MONGODB:-true}" = false ] || [ "${INSTALL_MONGODB:-true}" = "false" ]; then
        log_info "INSTALL_MONGODB=false -> skipping MongoDB installation"
        return 0
    fi
    
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
    # Try to install mongodb-org; if unmet dependencies (libssl1.1) occur on Ubuntu 22.04,
    # fail gracefully and instruct operator to use a managed DB or compatible package.
    if ! sudo apt-get install -y mongodb-org; then
        log_error "Failed to install mongodb-org using the upstream repo. This often happens on Ubuntu 22.04 because libssl1.1 is not available."
        log_warn "Recommended options:
  1) Use MongoDB Atlas or a remote MongoDB and set MONGO_URI in your .env (preferred).
  2) Install distro-packaged mongodb (e.g., mongodb from apt) manually if you need local DB.
  3) Install libssl1.1 from a trusted source (not recommended for production).
Skipping local MongoDB installation."
        return 0
    fi
    
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
    
    # Create or reuse the Python virtual environment
    if [ ! -d "venv" ]; then
        log "Creating Python virtual environment..."
        python3 -m venv venv
    else
        log "Reusing existing Python virtual environment"
    fi
    
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
    
    if ! command -v setfacl >/dev/null 2>&1; then
        log "Installing ACL utilities (acl package) for static asset permissions..."
        sudo apt-get install -y acl
    fi
    
    sudo setfacl -m u:www-data:rx "$(dirname "$PROJECT_DIR")"
    sudo setfacl -m u:www-data:rx "$PROJECT_DIR"
    sudo setfacl -R -m u:www-data:rx "$PROJECT_DIR/backend/app/static"
    sudo setfacl -R -d -m u:www-data:rx "$PROJECT_DIR/backend/app/static"
    chmod +x "$PROJECT_DIR"/scripts/*.sh 2>/dev/null || true
    chmod +x "$PROJECT_DIR"/deploy/*.sh 2>/dev/null || true
    
    log_success "Project environment setup completed"
}

# Configure environment variables
setup_environment() {
    header "CONFIGURING ENVIRONMENT VARIABLES"
    
    cd "$PROJECT_DIR"
    
    # Do NOT overwrite an existing .env. The server already has its own .env and should be kept.
    if [ -f .env ]; then
        log "Using existing .env file (will not overwrite)"
    else
        # If a per-server deploy/env file exists, use it to generate a minimal .env template
        if [ -f "$SCRIPT_DIR/env" ]; then
            log_warn "No project .env found; generating minimal .env from deploy/env"
            # Merge a small set of required vars into .env
            cat > .env << EOF
# Auto-generated minimal .env - please review and fill secrets
FLASK_APP=wsgi:app
FLASK_ENV=production
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
MONGO_URI=${MONGO_URI:-mongodb://localhost:27017/air_quality_db}
MONGO_DB_NAME=${MONGO_DB_NAME:-air_quality_db}
EOF
            log_warn "Generated minimal .env. Edit .env with API keys and credentials before running the app."
        else
            log_warn "No .env found and no deploy/env provided. Continuing but application may fail due to missing config."
        fi
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

    local host_name
    host_name=$(hostname)
    local external_ip="${PUBLIC_IP:-}"
    if [ -z "$external_ip" ]; then
        external_ip=$(curl -s https://api.ipify.org || curl -s http://checkip.amazonaws.com/ || echo "")
        PUBLIC_IP=$external_ip
    fi

    local domain_primary="${PRIMARY_DOMAIN:-}"
    local extra_domains="${ADDITIONAL_DOMAINS:-}"
    local server_names="$domain_primary $extra_domains"

    if [ -n "$external_ip" ]; then
        server_names="$server_names $external_ip"
    fi
    server_names="$server_names localhost $host_name _"
    server_names=$(echo "$server_names" | xargs)

    local cert_path="${SSL_CERT_PATH:-/etc/letsencrypt/live/${domain_primary}/fullchain.pem}"
    local key_path="${SSL_KEY_PATH:-/etc/letsencrypt/live/${domain_primary}/privkey.pem}"
    local https_ready=false
    if [ -n "$domain_primary" ] && sudo test -f "$cert_path" && sudo test -f "$key_path"; then
        https_ready=true
    fi

    if [ "$https_ready" = true ]; then
        sudo tee /etc/nginx/sites-available/air-quality-monitoring > /dev/null <<EOF
server {
    listen 80;
    server_name $server_names;
    return 301 https://$domain_primary\$request_uri;
}

server {
    listen 443 ssl;
    server_name $server_names;

    ssl_certificate $cert_path;
    ssl_certificate_key $key_path;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

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

    access_log $PROJECT_DIR/logs/nginx_access.log;
    error_log $PROJECT_DIR/logs/nginx_error.log;

    location /static/ {
        alias $PROJECT_DIR/backend/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location = /favicon.ico {
        alias $PROJECT_DIR/backend/app/static/favicon.ico;
        access_log off;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    location /api/health {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
}
EOF
    else
        sudo tee /etc/nginx/sites-available/air-quality-monitoring > /dev/null <<EOF
server {
    listen 80;
    server_name $server_names;

    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;

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

    access_log $PROJECT_DIR/logs/nginx_access.log;
    error_log $PROJECT_DIR/logs/nginx_error.log;

    location /static/ {
        alias $PROJECT_DIR/backend/app/static/;
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    location = /favicon.ico {
        alias $PROJECT_DIR/backend/app/static/favicon.ico;
        access_log off;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }

    location /api/health {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        access_log off;
    }

    location / {
        proxy_pass http://127.0.0.1:$SERVICE_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
        proxy_buffering on;
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
    }
}
EOF
    fi

    sudo ln -sf /etc/nginx/sites-available/air-quality-monitoring /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default

    if sudo nginx -t; then
        sudo systemctl reload nginx
    else
        log_error "Nginx configuration test failed"
        exit 1
    fi

    if [ "$https_ready" = true ]; then
        log_success "Nginx configured with HTTPS"
        if [ -n "$domain_primary" ]; then
            log "Site will be available at: https://$domain_primary"
        fi
    else
        log_success "Nginx configured (HTTP only)"
        if [ -n "$external_ip" ]; then
            log "Site will be available at: http://$external_ip"
        fi
        if [ -n "$domain_primary" ]; then
            log_warn "TLS certificate not yet detected for $domain_primary. Enable ENABLE_CERTBOT=true or run certbot manually once DNS is ready."
        fi
    fi
}


obtain_certificate() {
    header "REQUESTING TLS CERTIFICATE"

    if [ "${ENABLE_CERTBOT:-false}" != true ]; then
        log_info "ENABLE_CERTBOT is not true; skipping certificate request"
        return
    fi

    if [ -z "${PRIMARY_DOMAIN:-}" ]; then
        log_warn "PRIMARY_DOMAIN is not set; cannot request certificate"
        return
    fi

    local domains=("$PRIMARY_DOMAIN")
    if [ -n "${ADDITIONAL_DOMAINS:-}" ]; then
        for entry in ${ADDITIONAL_DOMAINS}; do
            domains+=("$entry")
        done
    fi

    local domain_args=()
    for d in "${domains[@]}"; do
        domain_args+=("-d" "$d")
    done

    if [ ${#domain_args[@]} -eq 0 ]; then
        log_warn "No domains provided to Certbot; skipping"
        return
    fi

    local email_args=("--register-unsafely-without-email")
    if [ -n "${CERTBOT_EMAIL:-}" ]; then
        email_args=("--email" "$CERTBOT_EMAIL" "--agree-tos")
    fi

    local staging_args=()
    if [ "${CERTBOT_USE_STAGING:-false}" = true ]; then
        staging_args=("--staging")
    fi

    log "Running certbot for: ${domains[*]}"
    if sudo certbot certonly --nginx --non-interactive --keep-until-expiring "${domain_args[@]}" "${email_args[@]}" "${staging_args[@]}" --deploy-hook "systemctl reload nginx"; then
        log_success "Certificate is in place for ${domains[0]}"
        CERT_OBTAINED=true
    else
        log_warn "Certbot failed to obtain certificate. Check DNS and rerun the script."
    fi
}


# Create systemd service
create_systemd_service() {
    header "CREATING SYSTEMD SERVICE"
    
    local after_line="After=network.target nginx.service"
    local wants_line=""
    if [ "${INSTALL_MONGODB:-true}" = true ]; then
        after_line="After=network.target mongod.service nginx.service"
        wants_line="Wants=mongod.service"
    fi

    sudo tee /etc/systemd/system/air-quality-monitoring.service << EOF
[Unit]
Description=Air Quality Monitoring System
$after_line
$wants_line
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
    
    if [ "${INSTALL_MONGODB:-true}" = true ]; then
        # Allow MongoDB (only locally)
        sudo ufw allow from 127.0.0.1 to any port 27017
    fi
    
    # Reload UFW
    sudo ufw reload
    
    log_success "Firewall configured successfully"
}

# Test application
test_application() {
    header "TESTING APPLICATION"

    if [ "$SKIP_TESTS" = true ]; then
        log_info "Skipping application test (--skip-tests flag set)"
        return 0
    fi

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
    if [ "${INSTALL_MONGODB:-true}" = true ]; then
        log "Ensuring MongoDB service is running..."
        sudo systemctl start mongod
        sleep 3
    else
        log_info "Skipping MongoDB service start (INSTALL_MONGODB=false)"
    fi

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

    log "Waiting for services to initialize..."
    sleep 10

    log "Testing local endpoints..."

    if curl -sf http://127.0.0.1:$SERVICE_PORT/api/health > /dev/null; then
        log_success "? Gunicorn responding"
    else
        log_error "? Gunicorn not responding"
        return 1
    fi

    if curl -sf http://localhost/api/health > /dev/null; then
        log_success "? Nginx proxy working"
    else
        log_error "? Nginx proxy not working"
        return 1
    fi

    if [ "${INSTALL_MONGODB:-true}" = true ]; then
        if mongosh --quiet --eval "db.runCommand('ping')" > /dev/null 2>&1; then
            log_success "? MongoDB responding"
        elif mongo --quiet --eval "db.runCommand('ping')" > /dev/null 2>&1; then
            log_success "? MongoDB responding (legacy client)"
        else
            log_warn "Could not verify MongoDB (but service may still work)"
        fi
    else
        log_info "Skipping MongoDB health check (INSTALL_MONGODB=false)"
    fi

    local targets=()
    if [ -n "${PUBLIC_URL:-}" ]; then
        targets+=("${PUBLIC_URL%/}/api/health")
    fi
    if [ -n "${PRIMARY_DOMAIN:-}" ]; then
        targets+=("https://$PRIMARY_DOMAIN/api/health")
        targets+=("http://$PRIMARY_DOMAIN/api/health")
    fi
    if [ -n "${PUBLIC_IP:-}" ]; then
        targets+=("http://$PUBLIC_IP/api/health")
    fi

    local external_ok=false
    local seen_urls=()

    if [ ${#targets[@]} -gt 0 ]; then
        log "Testing external access..."
        for url in "${targets[@]}"; do
            [ -z "$url" ] && continue
            url=${url%/}
            local skip=false
            for seen in "${seen_urls[@]}"; do
                if [ "$url" = "$seen" ]; then
                    skip=true
                    break
                fi
            done
            if [ "$skip" = true ]; then
                continue
            fi
            seen_urls+=("$url")
            if timeout 10 curl -sf "$url" > /dev/null; then
                log_success "? External access working via $url"
                external_ok=true
                break
            else
                log_warn "? External endpoint unreachable: $url"
            fi
        done

        if [ "$external_ok" = true ]; then
            EXTERNAL_ACCESS=true
        else
            log_warn "External reachability could not be confirmed"
            EXTERNAL_ACCESS=false
        fi
    else
        log_warn "No external targets configured for verification"
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

HAS_MONGOD=0
if systemctl list-unit-files --type=service --no-legend --no-pager | grep -q '^mongod.service'; then
    HAS_MONGOD=1
fi

echo "Service Status:"
if sudo systemctl is-active --quiet air-quality-monitoring.service; then
    echo "[OK] Application: RUNNING"
else
    echo "[ERR] Application: STOPPED"
fi
if sudo systemctl is-active --quiet nginx; then
    echo "[OK] Nginx: RUNNING"
else
    echo "[ERR] Nginx: STOPPED"
fi
if [ "$HAS_MONGOD" -eq 1 ]; then
    if sudo systemctl is-active --quiet mongod; then
        echo "[OK] MongoDB: RUNNING"
    else
        echo "[ERR] MongoDB: STOPPED"
    fi
else
    echo "[--] MongoDB: not managed locally"
fi

echo
echo "Port Status:"
PORT_REGEX=':(80|8000)'
if [ "$HAS_MONGOD" -eq 1 ]; then
    PORT_REGEX=':(80|8000|27017)'
fi
ss -tlnp | grep -E "$PORT_REGEX" || echo "No services listening on expected ports"

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

HAS_MONGOD=0
if systemctl list-unit-files --type=service --no-legend --no-pager | grep -q '^mongod.service'; then
    HAS_MONGOD=1
fi

if [ "$HAS_MONGOD" -eq 1 ]; then
    sudo systemctl restart mongod
fi
sudo systemctl restart air-quality-monitoring.service
sudo systemctl restart nginx
sleep 3
echo "Services restarted. Checking status:"
SERVICES="air-quality-monitoring.service nginx"
if [ "$HAS_MONGOD" -eq 1 ]; then
    SERVICES="$SERVICES mongod"
fi
for svc in $SERVICES; do
    if sudo systemctl is-active --quiet "$svc"; then
        echo "[OK] $svc is active"
    else
        echo "[ERR] $svc is not active"
    fi
done
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
    echo -e "${NC}
"

    log "Starting deployment at $(date)"

    check_root
    detect_system
    update_repository

    update_system
    install_python
    install_mongodb
    install_nginx

    setup_project
    setup_environment
    create_gunicorn_config
    configure_nginx
    obtain_certificate
    if [ "$CERT_OBTAINED" = true ]; then
        configure_nginx
    fi
    create_systemd_service

    configure_firewall

    test_application
    start_services
    verify_deployment
    create_management_scripts

    header "DEPLOYMENT COMPLETE"

    log_success "Air Quality Monitoring System deployment completed!"

    echo
    echo "System Information:"
    echo "  User: $SERVICE_USER"
    echo "  Project Path: $PROJECT_DIR"
    echo "  Python Workers: $WORKERS"
    if [ "$LOW_RESOURCE" = true ]; then
        echo "  Memory Optimization: Enabled"
    else
        echo "  Memory Optimization: Disabled"
    fi

    echo
    echo "Access Information:"
    echo "  Local: http://localhost"
    echo "  Direct: http://127.0.0.1:$SERVICE_PORT"
    local primary_domain_display="${PRIMARY_DOMAIN:-}"
    local active_cert=false
    if [ -n "$primary_domain_display" ] && sudo test -f "/etc/letsencrypt/live/$primary_domain_display/fullchain.pem"; then
        active_cert=true
    fi
    if [ -n "$primary_domain_display" ]; then
        if [ "$active_cert" = true ]; then
            echo "  Public: https://$primary_domain_display"
        else
            echo "  Public: http://$primary_domain_display"
        fi
    elif [ -n "$PUBLIC_IP" ]; then
        echo "  Public: http://$PUBLIC_IP"
        if [ "$EXTERNAL_ACCESS" = false ]; then
            echo "    Cloud firewall or security group may require port 80 access"
        fi
    fi

    echo
    echo "Management Commands:"
    echo "  ./status.sh"
    echo "  ./restart.sh"
    echo "  ./logs.sh"
    echo "  sudo systemctl {start|stop|restart|status} air-quality-monitoring"

    echo
    echo "Important Files:"
    echo "  .env"
    echo "  logs/"
    echo "  /etc/nginx/sites-available/air-quality-monitoring"
    echo "  /etc/systemd/system/air-quality-monitoring.service"

    echo
    echo "Next Steps:"
    echo "  1. Update .env with required configuration"
    echo "  2. Open port 80/443 in your cloud firewall if needed"
    echo "  3. Configure SSL for HTTPS (recommended)"
    echo "  4. Review email/alert settings (optional)"

    log_success "Deployment completed. Services should now be accessible."
}


## Run main function with error handling
# Write logs to a user-writable file to avoid permission denied when deploying as non-root
LOGFILE="$PROJECT_DIR/deploy_run.log"
touch "$LOGFILE" 2>/dev/null || LOGFILE="/tmp/air-quality-deploy-$(date +%s).log"
chmod 644 "$LOGFILE" 2>/dev/null || true

parse_args "$@"

main 2>&1 | tee "$LOGFILE"
STATUS=${PIPESTATUS[0]}

if [ "$STATUS" -eq 0 ]; then
    echo -e "\n${GREEN}🎯 Deployment log saved to: $LOGFILE${NC}"
    exit 0
else
    echo -e "\n${RED}💥 Deployment failed. Check the log above and $LOGFILE for details.${NC}"
    exit $STATUS
fi
