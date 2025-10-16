#!/bin/bash
# Air Quality Monitoring - Health Check Script
# Performs comprehensive health checks on deployed application
# Usage: ./health_check.sh [--verbose]

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
VERBOSE=false
for arg in "$@"; do
    case $arg in
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
    esac
done

# Load environment variables from .env safely
# This parser ignores comments/blank lines, trims whitespace around keys/values
# and removes surrounding single/double quotes from values.
if [ -f .env ]; then
    while IFS='=' read -r raw_key raw_val || [ -n "$raw_key" ]; do
        # Skip comments and empty lines
        if [[ "$raw_key" =~ ^\s*# ]] || [[ -z "$raw_key" ]]; then
            continue
        fi

        # Trim whitespace from key and value
        key="$(echo "$raw_key" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
        val="$(echo "$raw_val" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

        # Remove surrounding quotes if present
        val="${val%\"}"
        val="${val#\"}"
        val="${val%\'}"
        val="${val#\'}"

        # Only export non-empty keys
        if [ -n "$key" ]; then
            export "$key=$val"
        fi
    done < <(grep -v '^[[:space:]]*#' .env | grep -v '^[[:space:]]*$' || true)
else
    echo -e "${RED}Error: .env file not found${NC}"
    exit 1
fi

SERVICE_PORT="${SERVICE_PORT:-8000}"
PUBLIC_URL="${PUBLIC_URL:-http://localhost:$SERVICE_PORT}"
HEALTH_CHECKS_PASSED=0
HEALTH_CHECKS_FAILED=0

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Air Quality Monitoring - Health Check${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to mark test as passed
mark_passed() {
    echo -e "${GREEN}✓ $1${NC}"
    HEALTH_CHECKS_PASSED=$((HEALTH_CHECKS_PASSED + 1))
}

# Function to mark test as failed
mark_failed() {
    echo -e "${RED}✗ $1${NC}"
    HEALTH_CHECKS_FAILED=$((HEALTH_CHECKS_FAILED + 1))
}

# Function to mark test as warning
mark_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 1. Check systemd service status
echo -e "${YELLOW}[1] Checking systemd service...${NC}"
if sudo systemctl is-active --quiet gunicorn-aqi; then
    mark_passed "Gunicorn service is running"
    
    if [ "$VERBOSE" = true ]; then
        echo ""
        sudo systemctl status gunicorn-aqi --no-pager | head -n 10
        echo ""
    fi
else
    mark_failed "Gunicorn service is NOT running"
    sudo systemctl status gunicorn-aqi --no-pager | head -n 5
fi
echo ""

# 2. Check if service is listening on port
echo -e "${YELLOW}[2] Checking port binding...${NC}"
PORT_LISTENING=false
# Prefer ss (modern) then fall back to netstat if available
if command -v ss >/dev/null 2>&1; then
    if sudo ss -tlnp | grep -q ":$SERVICE_PORT"; then
        PORT_LISTENING=true
        if [ "$VERBOSE" = true ]; then
            sudo ss -tlnp | grep ":$SERVICE_PORT"
        fi
    fi
elif command -v netstat >/dev/null 2>&1; then
    if sudo netstat -tlnp | grep -q ":$SERVICE_PORT"; then
        PORT_LISTENING=true
        if [ "$VERBOSE" = true ]; then
            sudo netstat -tlnp | grep ":$SERVICE_PORT"
        fi
    fi
else
    mark_warning "Neither ss nor netstat available to check listening ports"
fi

if [ "$PORT_LISTENING" = true ]; then
    mark_passed "Service is listening on port $SERVICE_PORT"
else
    mark_failed "Service is NOT listening on port $SERVICE_PORT"
fi
echo ""

# 3. Check process count
echo -e "${YELLOW}[3] Checking Gunicorn processes...${NC}"
PROCESS_COUNT=$(pgrep -f "gunicorn.*backend.app.wsgi:app" | wc -l)
if [ "$PROCESS_COUNT" -gt 0 ]; then
    mark_passed "Found $PROCESS_COUNT Gunicorn process(es)"
    
    if [ "$VERBOSE" = true ]; then
        ps aux | grep -E "gunicorn.*backend.app.wsgi" | grep -v grep
    fi
else
    mark_failed "No Gunicorn processes found"
fi
echo ""

# 4. Check local HTTP response
echo -e "${YELLOW}[4] Checking local HTTP endpoint...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$SERVICE_PORT/ --connect-timeout 5 --max-time 10)
if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ] || [ "$HTTP_CODE" = "301" ]; then
    mark_passed "HTTP endpoint responding (Status: $HTTP_CODE)"
else
    mark_failed "HTTP endpoint not responding properly (Status: $HTTP_CODE)"
fi

if [ "$VERBOSE" = true ]; then
    echo "Full response:"
    curl -s http://localhost:$SERVICE_PORT/ | head -n 20
    echo ""
fi
echo ""

# 5. Check MongoDB connection (via app)
echo -e "${YELLOW}[5] Checking database connectivity...${NC}"
API_RESPONSE=$(curl -s http://localhost:$SERVICE_PORT/api/health --connect-timeout 5 --max-time 10 2>/dev/null)
if echo "$API_RESPONSE" | grep -q "ok\|healthy\|success" ; then
    mark_passed "Database connection verified via API"
    
    if [ "$VERBOSE" = true ]; then
        echo "Response: $API_RESPONSE"
    fi
elif [ -z "$API_RESPONSE" ]; then
    mark_warning "Health endpoint not available or not implemented"
else
    mark_failed "Database connection issue detected"
    echo "Response: $API_RESPONSE"
fi
echo ""

# 6. Check disk space
echo -e "${YELLOW}[6] Checking disk space...${NC}"
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -lt 80 ]; then
    mark_passed "Disk space OK (${DISK_USAGE}% used)"
else
    mark_warning "Disk space high (${DISK_USAGE}% used)"
fi

if [ "$VERBOSE" = true ]; then
    df -h /
fi
echo ""

# 7. Check memory usage
echo -e "${YELLOW}[7] Checking memory usage...${NC}"
MEMORY_AVAILABLE=$(free -m | awk 'NR==2 {print $7}')
if [ "$MEMORY_AVAILABLE" -gt 100 ]; then
    mark_passed "Memory available: ${MEMORY_AVAILABLE}MB"
else
    mark_warning "Low memory available: ${MEMORY_AVAILABLE}MB"
fi

if [ "$VERBOSE" = true ]; then
    free -h
fi
echo ""

# 8. Check log files for recent errors
echo -e "${YELLOW}[8] Checking recent error logs...${NC}"
if [ -f "logs/gunicorn-error.log" ]; then
    ERROR_COUNT=$(tail -n 100 logs/gunicorn-error.log 2>/dev/null | grep -ci "error\|exception\|critical" || echo "0")
    if [ "$ERROR_COUNT" -eq 0 ]; then
        mark_passed "No recent errors in logs"
    elif [ "$ERROR_COUNT" -lt 5 ]; then
        mark_warning "Found $ERROR_COUNT recent error(s) in logs"
    else
        mark_failed "Found $ERROR_COUNT recent error(s) in logs"
    fi
    
    if [ "$VERBOSE" = true ] && [ "$ERROR_COUNT" -gt 0 ]; then
        echo ""
        echo "Recent errors:"
        tail -n 100 logs/gunicorn-error.log | grep -i "error\|exception\|critical" | tail -n 5
    fi
else
    mark_warning "Log file not found: logs/gunicorn-error.log"
fi
echo ""

# 9. Check Nginx status
echo -e "${YELLOW}[9] Checking Nginx reverse proxy...${NC}"
if sudo systemctl is-active --quiet nginx; then
    mark_passed "Nginx is running"
    
    # Test Nginx configuration
    if sudo nginx -t 2>&1 | grep -q "successful"; then
        mark_passed "Nginx configuration is valid"
    else
        mark_failed "Nginx configuration has errors"
        if [ "$VERBOSE" = true ]; then
            sudo nginx -t
        fi
    fi
else
    mark_warning "Nginx is not running"
fi
echo ""

# 10. Check public URL (if accessible)
echo -e "${YELLOW}[10] Checking public URL...${NC}"
if [[ "$PUBLIC_URL" =~ ^https?:// ]]; then
    PUBLIC_HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$PUBLIC_URL" --connect-timeout 10 --max-time 15 2>/dev/null || echo "000")
    if [ "$PUBLIC_HTTP_CODE" = "200" ] || [ "$PUBLIC_HTTP_CODE" = "302" ] || [ "$PUBLIC_HTTP_CODE" = "301" ]; then
        mark_passed "Public URL is accessible (Status: $PUBLIC_HTTP_CODE)"
    else
        mark_warning "Public URL returned status: $PUBLIC_HTTP_CODE"
    fi
else
    mark_warning "Public URL not configured or not accessible from server"
fi
echo ""

# 11. Check recent service restarts
echo -e "${YELLOW}[11] Checking service stability...${NC}"
RESTART_COUNT=$(sudo journalctl -u gunicorn-aqi --since "1 hour ago" | grep -c "Started\|Stopped" || echo "0")
if [ "$RESTART_COUNT" -eq 0 ]; then
    mark_passed "Service has been stable (no restarts in last hour)"
elif [ "$RESTART_COUNT" -lt 3 ]; then
    mark_warning "Service restarted $RESTART_COUNT time(s) in last hour"
else
    mark_failed "Service unstable: $RESTART_COUNT restart(s) in last hour"
fi

if [ "$VERBOSE" = true ] && [ "$RESTART_COUNT" -gt 0 ]; then
    echo ""
    sudo journalctl -u gunicorn-aqi --since "1 hour ago" | grep "Started\|Stopped"
fi
echo ""

# 12. Check Python process resources
echo -e "${YELLOW}[12] Checking Python process resources...${NC}"
if [ "$PROCESS_COUNT" -gt 0 ]; then
    MAIN_PID=$(pgrep -f "gunicorn.*backend.app.wsgi:app" | head -n 1)
    CPU_USAGE=$(ps -p "$MAIN_PID" -o %cpu --no-headers 2>/dev/null | awk '{print int($1)}')
    MEM_USAGE=$(ps -p "$MAIN_PID" -o %mem --no-headers 2>/dev/null | awk '{print int($1)}')
    
    if [ -n "$CPU_USAGE" ] && [ -n "$MEM_USAGE" ]; then
        if [ "$CPU_USAGE" -lt 80 ] && [ "$MEM_USAGE" -lt 80 ]; then
            mark_passed "Process resources OK (CPU: ${CPU_USAGE}%, MEM: ${MEM_USAGE}%)"
        else
            mark_warning "High resource usage (CPU: ${CPU_USAGE}%, MEM: ${MEM_USAGE}%)"
        fi
        
        if [ "$VERBOSE" = true ]; then
            echo ""
            ps aux | grep -E "gunicorn.*backend.app.wsgi" | grep -v grep
        fi
    else
        mark_warning "Could not retrieve process resource usage"
    fi
else
    mark_failed "No process found to check"
fi
echo ""

# Summary
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Health Check Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Checks Passed: ${GREEN}$HEALTH_CHECKS_PASSED${NC}"
echo -e "Checks Failed: ${RED}$HEALTH_CHECKS_FAILED${NC}"
echo ""

if [ "$HEALTH_CHECKS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}✓ System is healthy!${NC}"
    exit 0
elif [ "$HEALTH_CHECKS_FAILED" -lt 3 ]; then
    echo -e "${YELLOW}⚠ System has minor issues${NC}"
    echo "Review failed checks above and consider investigating"
    exit 1
else
    echo -e "${RED}✗ System has critical issues${NC}"
    echo "Immediate attention required!"
    echo ""
    echo "Troubleshooting commands:"
    echo "  - Check service: sudo systemctl status gunicorn-aqi"
    echo "  - View logs: sudo journalctl -u gunicorn-aqi -n 50"
    echo "  - Check errors: tail -n 50 logs/gunicorn-error.log"
    echo "  - Restart service: sudo systemctl restart gunicorn-aqi"
    exit 2
fi
