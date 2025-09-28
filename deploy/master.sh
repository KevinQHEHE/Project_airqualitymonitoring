#!/bin/bash

################################################################################
# Air Quality Monitoring System - Master Control Script
# One script to rule them all
################################################################################

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

header() {
    echo -e "\n${PURPLE}================================${NC}"
    echo -e "${PURPLE}$1${NC}"
    echo -e "${PURPLE}================================${NC}\n"
}

show_banner() {
    echo -e "${CYAN}"
    echo "████████████████████████████████████████████████████████████████"
    echo "█                                                              █"
    echo "█          🌟 Air Quality Monitoring System 🌟                 █"
    echo "█                                                              █"
    echo "█              Universal Ubuntu Deployment                     █"
    echo "█                                                              █"
    echo "████████████████████████████████████████████████████████████████"
    echo -e "${NC}\n"
}

show_help() {
    echo -e "${BLUE}Usage: $0 [command]${NC}\n"
    echo "Available commands:"
    echo
    echo -e "${GREEN}🔍 Pre-deployment:${NC}"
    echo "  check        - Check system requirements before deployment"
    echo "  deploy       - Deploy the complete system (recommended)"
    echo
    echo -e "${GREEN}🛠️  Management:${NC}"
    echo "  status       - Show system status"
    echo "  health       - Run health check and show report"
    echo "  fix          - Auto-fix common issues"
    echo "  restart      - Restart all services"
    echo "  logs         - Show application logs"
    echo "  test         - Test all endpoints"
    echo
    echo -e "${GREEN}🔧 Advanced:${NC}"
    echo "  start        - Start all services"
    echo "  stop         - Stop all services"
    echo "  update       - Update and restart system"
    echo
    echo -e "${GREEN}📚 Information:${NC}"
    echo "  help         - Show this help message"
    echo "  version      - Show version information"
    echo "  info         - Show system information"
    echo
    echo -e "${YELLOW}💡 Quick Start:${NC}"
    echo "  1. Run: $0 check      (verify requirements)"
    echo "  2. Run: $0 deploy     (install everything)"
    echo "  3. Run: $0 health     (verify working)"
    echo
}

run_pre_check() {
    header "PRE-DEPLOYMENT CHECK"
    
    if [ -f "$SCRIPT_DIR/pre-check.sh" ]; then
        chmod +x "$SCRIPT_DIR/pre-check.sh"
        "$SCRIPT_DIR/pre-check.sh"
    else
        echo -e "${RED}Error: pre-check.sh not found${NC}"
        return 1
    fi
}

run_deploy() {
    header "STARTING DEPLOYMENT"
    
    echo -e "${YELLOW}This will install and configure the complete Air Quality Monitoring System.${NC}"
    echo -e "${YELLOW}The process will take 5-10 minutes depending on your server speed.${NC}"
    echo
    read -p "Continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -f "$SCRIPT_DIR/universal-deploy.sh" ]; then
            chmod +x "$SCRIPT_DIR/universal-deploy.sh"
            "$SCRIPT_DIR/universal-deploy.sh"
        else
            echo -e "${RED}Error: universal-deploy.sh not found${NC}"
            return 1
        fi
    else
        echo "Deployment cancelled."
    fi
}

run_health() {
    header "HEALTH CHECK"
    
    if [ -f "$SCRIPT_DIR/health-check.sh" ]; then
        chmod +x "$SCRIPT_DIR/health-check.sh"
        "$SCRIPT_DIR/health-check.sh" check
    else
        echo -e "${RED}Error: health-check.sh not found${NC}"
        return 1
    fi
}

run_fix() {
    header "AUTO-FIX"
    
    if [ -f "$SCRIPT_DIR/health-check.sh" ]; then
        chmod +x "$SCRIPT_DIR/health-check.sh"
        "$SCRIPT_DIR/health-check.sh" fix
    else
        echo -e "${RED}Error: health-check.sh not found${NC}"
        return 1
    fi
}

run_test() {
    header "ENDPOINT TESTING"
    
    if [ -f "$SCRIPT_DIR/health-check.sh" ]; then
        chmod +x "$SCRIPT_DIR/health-check.sh"
        "$SCRIPT_DIR/health-check.sh" test
    else
        echo -e "${RED}Error: health-check.sh not found${NC}"
        return 1
    fi
}

run_status() {
    header "SYSTEM STATUS"
    
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    
    if [ -f "$PROJECT_DIR/status.sh" ]; then
        "$PROJECT_DIR/status.sh"
    else
        # Fallback status check
        echo "=== Service Status ==="
        for service in air-quality-monitoring nginx mongod; do
            if systemctl is-active --quiet "$service" 2>/dev/null; then
                echo -e "${GREEN}✓ $service: RUNNING${NC}"
            else
                echo -e "${RED}✗ $service: STOPPED${NC}"
            fi
        done
        
        echo -e "\n=== Port Status ==="
        ss -tlnp | grep -E ':(80|8000|27017)\b' || echo "No services listening on expected ports"
    fi
}

run_logs() {
    header "APPLICATION LOGS"
    
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    
    if [ -f "$PROJECT_DIR/logs.sh" ]; then
        "$PROJECT_DIR/logs.sh"
    else
        # Fallback log viewing
        echo "=== Recent Application Logs ==="
        if [ -f "$PROJECT_DIR/logs/error.log" ]; then
            echo "--- Error Log (last 10 lines) ---"
            tail -10 "$PROJECT_DIR/logs/error.log"
        fi
        
        if [ -f "$PROJECT_DIR/logs/access.log" ]; then
            echo -e "\n--- Access Log (last 5 lines) ---"
            tail -5 "$PROJECT_DIR/logs/access.log"
        fi
        
        echo -e "\n--- System Service Log ---"
        journalctl -u air-quality-monitoring -n 10 --no-pager 2>/dev/null || echo "No service logs available"
    fi
}

run_restart() {
    header "RESTARTING SERVICES"
    
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    
    if [ -f "$PROJECT_DIR/restart.sh" ]; then
        "$PROJECT_DIR/restart.sh"
    else
        # Fallback restart
        echo "Restarting services..."
        sudo systemctl restart air-quality-monitoring nginx mongod
        sleep 3
        echo "Services restarted."
        run_status
    fi
}

run_start() {
    header "STARTING SERVICES"
    
    echo "Starting all services..."
    sudo systemctl start mongod
    sudo systemctl start air-quality-monitoring
    sudo systemctl start nginx
    sleep 3
    echo "Services started."
    run_status
}

run_stop() {
    header "STOPPING SERVICES"
    
    echo "Stopping all services..."
    sudo systemctl stop air-quality-monitoring
    sudo systemctl stop nginx
    echo "Services stopped."
}

run_update() {
    header "UPDATING SYSTEM"
    
    echo "Updating packages and restarting services..."
    sudo apt update
    run_restart
}

show_version() {
    echo -e "${GREEN}Air Quality Monitoring System${NC}"
    echo "Version: 1.0.0"
    echo "Compatible with: Ubuntu 18.04+"
    echo "Python: 3.8+"
    echo "MongoDB: 6.0+"
    echo "Nginx: Latest"
    echo
    echo "Deployment Package: Universal"
}

show_info() {
    header "SYSTEM INFORMATION"
    
    echo "=== Server Info ==="
    echo "OS: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')"
    echo "Kernel: $(uname -r)"
    echo "Architecture: $(uname -m)"
    echo "User: $(whoami)"
    echo "Hostname: $(hostname)"
    
    echo -e "\n=== Resources ==="
    echo "Memory: $(free -h | awk 'NR==2{printf "Total: %s, Available: %s", $2, $7}')"
    echo "Disk: $(df -h . | awk 'NR==2{printf "Total: %s, Available: %s", $2, $4}')"
    echo "CPU Cores: $(nproc)"
    
    echo -e "\n=== Network ==="
    PUBLIC_IP=$(curl -s https://api.ipify.org 2>/dev/null || echo "Unknown")
    echo "Public IP: $PUBLIC_IP"
    echo "Local IPs: $(hostname -I | xargs)"
    
    echo -e "\n=== Project ==="
    PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
    echo "Project Directory: $PROJECT_DIR"
    echo "Deployment Scripts: $SCRIPT_DIR"
    
    if [ -f "$PROJECT_DIR/.env" ]; then
        echo "Configuration: ✓ .env file exists"
    else
        echo "Configuration: ⚠ .env file missing"
    fi
}

main() {
    show_banner
    
    case "${1:-help}" in
        "check"|"precheck")
            run_pre_check
            ;;
        "deploy")
            run_deploy
            ;;
        "health")
            run_health
            ;;
        "fix")
            run_fix
            ;;
        "test")
            run_test
            ;;
        "status")
            run_status
            ;;
        "logs")
            run_logs
            ;;
        "restart")
            run_restart
            ;;
        "start")
            run_start
            ;;
        "stop")
            run_stop
            ;;
        "update")
            run_update
            ;;
        "version")
            show_version
            ;;
        "info")
            show_info
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            echo -e "${RED}Unknown command: $1${NC}\n"
            show_help
            exit 1
            ;;
    esac
}

main "$@"