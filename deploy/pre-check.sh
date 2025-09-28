#!/bin/bash

################################################################################
# Pre-deployment System Requirements Check
# Verifies server meets minimum requirements before deployment
################################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log() { echo -e "${GREEN}[CHECK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }

header() {
    echo -e "\n${PURPLE}================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}================================${NC}\n"
}

ERRORS=0
WARNINGS=0

header "PRE-DEPLOYMENT SYSTEM REQUIREMENTS CHECK"

# Check operating system
check_os() {
    log_info "Checking operating system..."
    
    if [ ! -f /etc/os-release ]; then
        log_error "Cannot determine operating system"
        ((ERRORS++))
        return 1
    fi
    
    . /etc/os-release
    
    case "$ID" in
        ubuntu)
            log "✓ Ubuntu detected: $PRETTY_NAME"
            
            # Check version
            VERSION_NUM=$(echo "$VERSION_ID" | cut -d. -f1)
            if [ "$VERSION_NUM" -ge 18 ]; then
                log "✓ Ubuntu version supported ($VERSION_ID)"
            else
                log_error "Ubuntu version too old. Requires 18.04 or newer, found $VERSION_ID"
                ((ERRORS++))
            fi
            ;;
        *)
            log_error "Unsupported OS: $PRETTY_NAME"
            log_error "This script only supports Ubuntu Linux"
            ((ERRORS++))
            ;;
    esac
}

# Check system resources
check_resources() {
    log_info "Checking system resources..."
    
    # Check memory
    TOTAL_MEM=$(free -m | awk 'NR==2{printf "%.0f", $2}')
    log "Total memory: ${TOTAL_MEM}MB"
    
    if [ "$TOTAL_MEM" -lt 512 ]; then
        log_error "Insufficient memory. Minimum 512MB required, found ${TOTAL_MEM}MB"
        ((ERRORS++))
    elif [ "$TOTAL_MEM" -lt 1024 ]; then
        log_warn "Low memory detected (${TOTAL_MEM}MB). 1GB+ recommended for optimal performance"
        ((WARNINGS++))
    else
        log "✓ Memory sufficient (${TOTAL_MEM}MB)"
    fi
    
    # Check disk space
    AVAILABLE_GB=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    log "Available disk space: ${AVAILABLE_GB}GB"
    
    if [ "$AVAILABLE_GB" -lt 3 ]; then
        log_error "Insufficient disk space. Minimum 3GB required, found ${AVAILABLE_GB}GB"
        ((ERRORS++))
    elif [ "$AVAILABLE_GB" -lt 5 ]; then
        log_warn "Low disk space (${AVAILABLE_GB}GB). 5GB+ recommended"
        ((WARNINGS++))
    else
        log "✓ Disk space sufficient (${AVAILABLE_GB}GB)"
    fi
    
    # Check CPU
    CPU_CORES=$(nproc)
    log "CPU cores: $CPU_CORES"
    
    if [ "$CPU_CORES" -lt 1 ]; then
        log_error "No CPU cores detected"
        ((ERRORS++))
    else
        log "✓ CPU cores available ($CPU_CORES)"
    fi
}

# Check user permissions
check_permissions() {
    log_info "Checking user permissions..."
    
    # Check if not root
    if [[ $EUID -eq 0 ]]; then
        log_error "Running as root user. Please run as a regular user with sudo privileges"
        ((ERRORS++))
        return 1
    else
        log "✓ Not running as root user"
    fi
    
    # Check sudo access
    if sudo -n true 2>/dev/null; then
        log "✓ Passwordless sudo access available"
    elif echo "test" | sudo -S true 2>/dev/null; then
        log "✓ Sudo access available (may prompt for password)"
    else
        log_error "No sudo access. Please ensure user has sudo privileges"
        ((ERRORS++))
    fi
}

# Check internet connectivity
check_internet() {
    log_info "Checking internet connectivity..."
    
    # Check basic connectivity
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        log "✓ Internet connectivity available"
    else
        log_error "No internet connectivity. Required for downloading packages"
        ((ERRORS++))
        return 1
    fi
    
    # Check HTTPS access (for package downloads)
    if curl -sf https://api.ipify.org >/dev/null 2>&1; then
        log "✓ HTTPS access working"
    else
        log_warn "HTTPS access may be limited. Could affect package downloads"
        ((WARNINGS++))
    fi
    
    # Check specific package repositories
    if curl -sf http://archive.ubuntu.com/ubuntu >/dev/null 2>&1; then
        log "✓ Ubuntu package repository accessible"
    else
        log_warn "Ubuntu package repository may be inaccessible"
        ((WARNINGS++))
    fi
}

# Check existing services/ports
check_ports() {
    log_info "Checking port availability..."
    
    # Check port 80 (HTTP)
    if ss -ln | grep -q ":80 "; then
        log_warn "Port 80 already in use. May conflict with Nginx"
        ((WARNINGS++))
    else
        log "✓ Port 80 available"
    fi
    
    # Check port 8000 (Gunicorn)
    if ss -ln | grep -q ":8000 "; then
        log_warn "Port 8000 already in use. May conflict with application"
        ((WARNINGS++))
    else
        log "✓ Port 8000 available"
    fi
    
    # Check port 27017 (MongoDB)
    if ss -ln | grep -q ":27017 "; then
        log_warn "Port 27017 already in use. May conflict with MongoDB"
        ((WARNINGS++))
    else
        log "✓ Port 27017 available"
    fi
}

# Check for conflicting services
check_services() {
    log_info "Checking for conflicting services..."
    
    # Check for existing web servers
    for service in apache2 httpd lighttpd; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            log_warn "$service is running and may conflict with Nginx"
            ((WARNINGS++))
        fi
    done
    
    # Check for existing MongoDB
    if systemctl is-active --quiet mongod 2>/dev/null; then
        log_warn "MongoDB is already running. Will use existing installation"
        ((WARNINGS++))
    fi
    
    # Check for existing Nginx
    if systemctl is-active --quiet nginx 2>/dev/null; then
        log_warn "Nginx is already running. Configuration will be modified"
        ((WARNINGS++))
    fi
}

# Check Python availability
check_python() {
    log_info "Checking Python availability..."
    
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
        PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
        PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
        
        log "Found Python $PYTHON_VERSION"
        
        if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 8 ]; then
            log "✓ Python version supported ($PYTHON_VERSION)"
        elif [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 6 ]; then
            log_warn "Python $PYTHON_VERSION detected. Python 3.8+ recommended"
            ((WARNINGS++))
        else
            log_error "Python version too old. Requires 3.6+, found $PYTHON_VERSION"
            ((ERRORS++))
        fi
    else
        log_warn "Python3 not found. Will be installed during deployment"
        ((WARNINGS++))
    fi
    
    # Check pip availability
    if command -v pip3 >/dev/null 2>&1; then
        log "✓ pip3 available"
    else
        log_warn "pip3 not found. Will be installed during deployment"
        ((WARNINGS++))
    fi
}

# Check project files
check_project_files() {
    log_info "Checking project files..."
    
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    
    # Check essential files
    REQUIRED_FILES=(
        "wsgi.py"
        "requirements.txt"
        "backend/app/__init__.py"
        "backend/app/config.py"
    )
    
    for file in "${REQUIRED_FILES[@]}"; do
        if [ -f "$PROJECT_DIR/$file" ]; then
            log "✓ Found $file"
        else
            log_error "Missing required file: $file"
            ((ERRORS++))
        fi
    done
    
    # Check deployment script
    if [ -f "$SCRIPT_DIR/universal-deploy.sh" ]; then
        log "✓ Deployment script found"
        
        # Check if executable
        if [ -x "$SCRIPT_DIR/universal-deploy.sh" ]; then
            log "✓ Deployment script is executable"
        else
            log_warn "Deployment script is not executable. Run: chmod +x deploy/universal-deploy.sh"
            ((WARNINGS++))
        fi
    else
        log_error "Deployment script not found: deploy/universal-deploy.sh"
        ((ERRORS++))
    fi
}

# Generate final report
generate_report() {
    header "PRE-DEPLOYMENT CHECK RESULTS"
    
    echo "📊 Summary:"
    echo "  • Errors: $ERRORS"
    echo "  • Warnings: $WARNINGS"
    echo
    
    if [ $ERRORS -eq 0 ]; then
        echo -e "${GREEN}✅ READY FOR DEPLOYMENT${NC}"
        echo
        echo "Your system meets all requirements for deployment."
        echo "You can now run the deployment script:"
        echo
        echo -e "${BLUE}    ./deploy/universal-deploy.sh${NC}"
        echo
        
        if [ $WARNINGS -gt 0 ]; then
            echo -e "${YELLOW}⚠️  Note: $WARNINGS warnings detected${NC}"
            echo "The deployment should work, but consider addressing the warnings above."
        fi
        
        return 0
    else
        echo -e "${RED}❌ NOT READY FOR DEPLOYMENT${NC}"
        echo
        echo "Please fix the $ERRORS error(s) above before running deployment."
        echo
        echo "Common fixes:"
        echo "  • Ensure you're on Ubuntu 18.04 or newer"
        echo "  • Add user to sudo group: sudo usermod -aG sudo \$USER"
        echo "  • Free up disk space if needed"
        echo "  • Ensure internet connectivity"
        echo
        return 1
    fi
}

# Main execution
main() {
    echo -e "${PURPLE}"
    echo "################################################################################"
    echo "#                    Pre-Deployment Requirements Check                        #"
    echo "################################################################################"
    echo -e "${NC}\n"
    
    check_os
    check_resources
    check_permissions
    check_internet
    check_ports
    check_services
    check_python
    check_project_files
    
    generate_report
}

main "$@"