#!/bin/bash
# Air Quality Monitoring - Automated Deployment Script
# This script handles complete deployment workflow: pull code, install dependencies, restart services
# Usage: ./deploy.sh [--skip-backup] [--skip-pull]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
    done < <(grep -v '^\s*#' .env | grep -v '^\s*$' || true)
else
    echo -e "${RED}Error: .env file not found${NC}"
    exit 1
fi

# Set defaults from .env
PROJECT_DIR="${PROJECT_DIR:-/home/azureuser/air-quality-monitoring}"
SERVICE_USER="${SERVICE_USER:-azureuser}"
SERVICE_PORT="${SERVICE_PORT:-8000}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
WORKERS=2  # Conservative for 848MB RAM

# Parse arguments
SKIP_BACKUP=false
SKIP_PULL=false
for arg in "$@"; do
    case $arg in
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --skip-pull)
            SKIP_PULL=true
            shift
            ;;
    esac
done

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Air Quality Monitoring - Deployment${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Navigate to project directory
echo -e "${YELLOW}[1/9] Navigating to project directory...${NC}"
cd "$PROJECT_DIR" || exit 1
echo -e "${GREEN}✓ Current directory: $(pwd)${NC}"
echo ""

# Step 2: Backup current state (optional)
if [ "$SKIP_BACKUP" = false ]; then
    echo -e "${YELLOW}[2/9] Creating backup of current deployment...${NC}"
    BACKUP_DIR="$PROJECT_DIR/deploy_backups"
    mkdir -p "$BACKUP_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$BACKUP_DIR/backup_$TIMESTAMP.tar.gz"
    
    tar -czf "$BACKUP_FILE" \
        --exclude='deploy_backups' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.git' \
        --exclude='venv' \
        --exclude='backup_dtb/backup_data' \
        . 2>/dev/null || echo "Warning: Some files skipped during backup"
    
    # Keep only last 5 backups
    ls -t "$BACKUP_DIR"/backup_*.tar.gz | tail -n +6 | xargs -r rm --
    echo -e "${GREEN}✓ Backup created: $BACKUP_FILE${NC}"
else
    echo -e "${YELLOW}[2/9] Skipping backup (--skip-backup flag)${NC}"
fi
echo ""

# Step 3: Pull latest code
if [ "$SKIP_PULL" = false ]; then
    echo -e "${YELLOW}[3/9] Pulling latest code from Git...${NC}"
    git fetch "$GIT_REMOTE"
    
    # Check for local changes
    if ! git diff-index --quiet HEAD --; then
        echo -e "${RED}Warning: Local changes detected. Stashing...${NC}"
        git stash save "Auto-stash before deploy $(date)"
    fi
    
    git checkout "$GIT_BRANCH"
    git pull "$GIT_REMOTE" "$GIT_BRANCH"
    echo -e "${GREEN}✓ Code updated to latest version${NC}"
else
    echo -e "${YELLOW}[3/9] Skipping git pull (--skip-pull flag)${NC}"
fi
echo ""

# Step 4: Activate virtual environment or create if not exists
echo -e "${YELLOW}[4/9] Setting up Python virtual environment...${NC}"
if [ ! -d "venv" ]; then
    echo "Creating new virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo ""

# Step 5: Install/Update dependencies
echo -e "${YELLOW}[5/9] Installing Python dependencies...${NC}"
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
pip install gunicorn  # Ensure gunicorn is installed
echo -e "${GREEN}✓ Dependencies installed${NC}"
echo ""

# Step 6: Verify critical files
echo -e "${YELLOW}[6/9] Verifying deployment files...${NC}"
CRITICAL_FILES=(
    ".env"
    "backend/app/__init__.py"
    "backend/app/wsgi.py"
    "requirements.txt"
)

for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo -e "${RED}Error: Critical file missing: $file${NC}"
        exit 1
    fi
done
echo -e "${GREEN}✓ All critical files present${NC}"
echo ""

# Step 7: Stop existing Gunicorn service
echo -e "${YELLOW}[7/9] Stopping existing Gunicorn service...${NC}"
if sudo systemctl is-active --quiet gunicorn-aqi; then
    sudo systemctl stop gunicorn-aqi
    echo -e "${GREEN}✓ Service stopped${NC}"
else
    echo "Service not running (will be started)"
fi
echo ""

# Step 8: Create/Update systemd service
echo -e "${YELLOW}[8/9] Configuring systemd service...${NC}"
sudo tee /etc/systemd/system/gunicorn-aqi.service > /dev/null <<EOF
[Unit]
Description=Gunicorn instance for Air Quality Monitoring
After=network.target

[Service]
Type=notify
User=$SERVICE_USER
Group=www-data
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/venv/bin/gunicorn \\
    --bind 0.0.0.0:$SERVICE_PORT \\
    --workers $WORKERS \\
    --threads 2 \\
    --worker-class sync \\
    --timeout 300 \\
    --max-requests 1000 \\
    --max-requests-jitter 50 \\
    --access-logfile $PROJECT_DIR/logs/gunicorn-access.log \\
    --error-logfile $PROJECT_DIR/logs/gunicorn-error.log \\
    --log-level info \\
    --capture-output \\
    backend.app.wsgi:app

ExecReload=/bin/kill -s HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=30
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create logs directory and set ownership (use sudo if not root)
mkdir -p "$PROJECT_DIR/logs"
if [ "$(id -u)" -eq 0 ]; then
    chown -R "$SERVICE_USER":www-data "$PROJECT_DIR/logs" || echo "Warning: chown failed"
else
    # Try with sudo; if sudo fails, warn but continue
    sudo chown -R "$SERVICE_USER":www-data "$PROJECT_DIR/logs" 2>/dev/null || \
        echo "Warning: unable to change ownership of $PROJECT_DIR/logs (sudo may be required)"
fi

sudo systemctl daemon-reload
echo -e "${GREEN}✓ Systemd service configured${NC}"
echo ""

# Step 9: Start and enable service
echo -e "${YELLOW}[9/9] Starting Gunicorn service...${NC}"
sudo systemctl enable gunicorn-aqi
sudo systemctl start gunicorn-aqi

# Wait for service to start
sleep 3

if sudo systemctl is-active --quiet gunicorn-aqi; then
    echo -e "${GREEN}✓ Service started successfully${NC}"
else
    echo -e "${RED}Error: Service failed to start${NC}"
    echo "Checking logs..."
    sudo journalctl -u gunicorn-aqi -n 20 --no-pager
    exit 1
fi
echo ""

# Step 10: Reload Nginx
echo -e "${YELLOW}[Extra] Reloading Nginx...${NC}"
if sudo systemctl is-active --quiet nginx; then
    sudo nginx -t && sudo systemctl reload nginx
    echo -e "${GREEN}✓ Nginx reloaded${NC}"
else
    echo -e "${YELLOW}Warning: Nginx not running${NC}"
fi
echo ""

# Final status check
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Deployment Summary${NC}"
echo -e "${BLUE}========================================${NC}"
echo -e "Service Status: $(sudo systemctl is-active gunicorn-aqi)"
echo -e "Service Port: $SERVICE_PORT"
echo -e "Workers: $WORKERS"
echo -e "Project Dir: $PROJECT_DIR"
echo ""

# Show last few log lines
echo -e "${YELLOW}Recent logs:${NC}"
sudo journalctl -u gunicorn-aqi -n 5 --no-pager

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Deployment completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "Next steps:"
echo -e "  1. Run health check: ${BLUE}./deploy/health_check.sh${NC}"
echo -e "  2. View logs: ${BLUE}sudo journalctl -u gunicorn-aqi -f${NC}"
echo -e "  3. Check service: ${BLUE}sudo systemctl status gunicorn-aqi${NC}"
echo ""
