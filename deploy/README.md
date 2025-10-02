# Air Quality Monitoring - Deployment Guide

## Overview

This deployment system provides automated, reliable deployment of the Air Quality Monitoring application on Ubuntu server using Gunicorn and systemd.

**Key Features:**
- ✅ Automated Git pull and dependency installation
- ✅ Zero-downtime deployment with systemd service management
- ✅ Automatic backup before deployment
- ✅ Comprehensive health checking
- ✅ Optimized for low-memory environments (848MB RAM)
- ✅ Production-ready Gunicorn configuration

## Prerequisites

### Server Requirements
- Ubuntu 20.04+ (tested on your VM)
- Python 3.8+
- Git installed
- Nginx configured (already done on your server)
- SSH access with sudo privileges

### Project Setup
1. Project cloned to `/home/azureuser/air-quality-monitoring`
2. `.env` file configured with all required variables
3. Nginx reverse proxy configured to forward to Gunicorn

## Quick Start

### 1. Initial Deployment

```bash
# SSH into your server
ssh azureuser@<your-server-ip>

# Navigate to project
cd /home/azureuser/air-quality-monitoring

# Make scripts executable
chmod +x deploy/deploy.sh deploy/health_check.sh

# Run deployment
./deploy/deploy.sh
```

### 2. Verify Deployment

```bash
# Run health check
./deploy/health_check.sh

# Check service status
sudo systemctl status gunicorn-aqi

# View live logs
sudo journalctl -u gunicorn-aqi -f
```

### 3. Subsequent Deployments

Every time you need to deploy new code:

```bash
cd /home/azureuser/air-quality-monitoring
./deploy/deploy.sh
```

That's it! The script handles everything automatically.

## Configuration

All configuration is read from `.env` file. Key deployment variables:

```env
# Server Configuration
SERVICE_USER=azureuser              # User running the service
PROJECT_DIR=/home/azureuser/air-quality-monitoring
SERVICE_PORT=8000                   # Gunicorn port (Nginx proxies to this)
NGINX_PORT=80                       # Public facing port

# Git Configuration
GIT_REMOTE=origin                   # Git remote name
GIT_BRANCH=main                     # Branch to deploy

# Domain Configuration
PRIMARY_DOMAIN=airqualitymonitor.page
PUBLIC_URL=https://airqualitymonitor.page
```

## Deployment Scripts

### `deploy.sh`

Main deployment script that handles the complete deployment workflow.

**What it does:**
1. Navigates to project directory
2. Creates backup of current deployment
3. Pulls latest code from Git
4. Sets up Python virtual environment
5. Installs/updates dependencies
6. Verifies critical files
7. Stops existing Gunicorn service
8. Creates/updates systemd service configuration
9. Starts and enables service
10. Reloads Nginx

**Usage:**
```bash
# Standard deployment
./deploy/deploy.sh

# Skip backup (faster, but no rollback)
./deploy/deploy.sh --skip-backup

# Skip git pull (deploy local changes)
./deploy/deploy.sh --skip-pull

# Combine flags
./deploy/deploy.sh --skip-backup --skip-pull
```

**Options:**
- `--skip-backup`: Skip creating deployment backup (faster)
- `--skip-pull`: Skip git pull (useful for testing local changes)

### `health_check.sh`

Comprehensive health check script to verify deployment.

**What it checks:**
1. ✅ Systemd service status
2. ✅ Port binding (service listening)
3. ✅ Gunicorn processes
4. ✅ HTTP endpoint responsiveness
5. ✅ Database connectivity
6. ✅ Disk space
7. ✅ Memory usage
8. ✅ Recent error logs
9. ✅ Nginx status and configuration
10. ✅ Public URL accessibility
11. ✅ Service stability (restart count)
12. ✅ Process resource usage

**Usage:**
```bash
# Standard health check
./deploy/health_check.sh

# Verbose mode (detailed output)
./deploy/health_check.sh --verbose
```

**Exit Codes:**
- `0`: All checks passed (healthy)
- `1`: Minor issues detected (investigate)
- `2`: Critical issues (immediate attention required)

## Gunicorn Configuration

The deployment uses a production-ready Gunicorn configuration optimized for your server:

```ini
Workers: 2                          # Conservative for 848MB RAM
Threads per worker: 2               # Total 4 threads
Worker class: sync                  # Standard synchronous workers
Timeout: 300s                       # 5 minutes (for long-running requests)
Max requests: 1000                  # Recycle workers after 1000 requests
Max requests jitter: 50             # Random jitter for worker recycling
```

**Why these settings?**
- **2 workers**: Formula is `(2 * CPU cores) + 1`, but limited by 848MB RAM
- **Sync workers**: More memory-efficient than async for this workload
- **High timeout**: Accommodates data ingest and API calls to external services
- **Worker recycling**: Prevents memory leaks from accumulating

## Systemd Service

Service name: `gunicorn-aqi`

The deployment creates a systemd service at `/etc/systemd/system/gunicorn-aqi.service`.

**Service management:**
```bash
# Start service
sudo systemctl start gunicorn-aqi

# Stop service
sudo systemctl stop gunicorn-aqi

# Restart service
sudo systemctl restart gunicorn-aqi

# Reload service (graceful restart)
sudo systemctl reload gunicorn-aqi

# Enable on boot
sudo systemctl enable gunicorn-aqi

# Disable on boot
sudo systemctl disable gunicorn-aqi

# Check status
sudo systemctl status gunicorn-aqi

# View logs
sudo journalctl -u gunicorn-aqi -f
```

**Service features:**
- ✅ Auto-restart on failure (with 10s delay)
- ✅ Graceful reload support (HUP signal)
- ✅ Runs as `azureuser` user
- ✅ Environment variables from `.env`
- ✅ Logs to `logs/gunicorn-access.log` and `logs/gunicorn-error.log`

## File Structure

```
deploy/
├── deploy.sh           # Main deployment script
├── health_check.sh     # Health check script
└── README.md          # This file

logs/                   # Created by deployment
├── gunicorn-access.log
└── gunicorn-error.log

deploy_backups/        # Created by deployment
├── backup_20250102_143000.tar.gz
└── backup_20250102_150000.tar.gz
```

## Troubleshooting

### Service won't start

```bash
# Check service status
sudo systemctl status gunicorn-aqi

# View recent logs
sudo journalctl -u gunicorn-aqi -n 50

# Check error log
tail -n 50 logs/gunicorn-error.log

# Test Gunicorn manually
cd /home/azureuser/air-quality-monitoring
source venv/bin/activate
gunicorn backend.app.wsgi:app --bind 0.0.0.0:8000
```

### Port already in use

```bash
# Find what's using the port
sudo netstat -tlnp | grep :8000

# Kill the process
sudo kill <PID>

# Or restart the service
sudo systemctl restart gunicorn-aqi
```

### Memory issues

```bash
# Check memory usage
free -h

# Check swap
swapon --show

# View process memory
ps aux --sort=-%mem | head

# Reduce workers if needed (edit systemd service)
sudo systemctl edit gunicorn-aqi
```

### Application errors

```bash
# Check application logs
tail -f logs/gunicorn-error.log

# Check systemd logs
sudo journalctl -u gunicorn-aqi -f

# Test database connection
python3 -c "from backend.app.db import test_connection; test_connection()"
```

### Nginx issues

```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# View Nginx error log
sudo tail -f /var/log/nginx/error.log

# Check Nginx access log
sudo tail -f /var/log/nginx/access.log
```

### Git conflicts

If deployment fails due to local changes:

```bash
# View changes
git status
git diff

# Stash changes
git stash

# Or reset to remote
git reset --hard origin/main

# Then redeploy
./deploy/deploy.sh
```

### Rollback deployment

If new deployment has issues, restore from backup:

```bash
# Stop service
sudo systemctl stop gunicorn-aqi

# List backups
ls -lh deploy_backups/

# Extract backup (replace with your backup file)
tar -xzf deploy_backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Restart service
sudo systemctl start gunicorn-aqi

# Verify
./deploy/health_check.sh
```

## Monitoring

### View logs in real-time

```bash
# Application logs
tail -f logs/gunicorn-error.log logs/gunicorn-access.log

# Systemd logs
sudo journalctl -u gunicorn-aqi -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

### Check resource usage

```bash
# Overall system
htop

# Gunicorn processes
ps aux | grep gunicorn

# Memory
free -h

# Disk
df -h
```

### Automated monitoring

Set up a cron job for periodic health checks:

```bash
# Edit crontab
crontab -e

# Add health check every 5 minutes (logs to file)
*/5 * * * * /home/azureuser/air-quality-monitoring/deploy/health_check.sh >> /home/azureuser/health-check.log 2>&1
```

## Performance Tuning

### For higher traffic

If you need better performance and have more RAM:

1. Edit `/etc/systemd/system/gunicorn-aqi.service`
2. Increase workers: `--workers 4`
3. Increase threads: `--threads 4`
4. Reload: `sudo systemctl daemon-reload && sudo systemctl restart gunicorn-aqi`

### For memory constrained

If experiencing memory issues:

1. Reduce workers: `--workers 1`
2. Use worker recycling more aggressively: `--max-requests 500`
3. Consider using gevent workers: `--worker-class gevent` (requires `pip install gevent`)

## Security Notes

- ✅ Service runs as non-root user (`azureuser`)
- ✅ Environment variables loaded from `.env` (not exposed)
- ✅ Logs stored in project directory (not world-readable)
- ✅ Nginx handles HTTPS termination
- ✅ Gunicorn binds to `0.0.0.0:8000` (internal only, proxied by Nginx)

**Important:** Never commit `.env` to Git! It contains sensitive credentials.

## Deployment Checklist

Before each deployment:

- [ ] Test code locally or in staging
- [ ] Review Git changes: `git log origin/main..main`
- [ ] Backup database (if schema changes)
- [ ] Check `.env` for new required variables
- [ ] Verify server has enough disk space: `df -h`
- [ ] Verify server has enough memory: `free -h`
- [ ] Schedule during low-traffic period (if critical)

After deployment:

- [ ] Run health check: `./deploy/health_check.sh --verbose`
- [ ] Test critical endpoints manually
- [ ] Monitor logs for 5-10 minutes: `sudo journalctl -u gunicorn-aqi -f`
- [ ] Check public URL: `curl -I https://airqualitymonitor.page`
- [ ] Verify background tasks still running (if any)

## Support

If issues persist:

1. Collect diagnostics:
   ```bash
   ./deploy/health_check.sh --verbose > health-report.txt
   sudo journalctl -u gunicorn-aqi -n 100 > service-logs.txt
   ```

2. Review project documentation:
   - `docs/architecture.md`
   - `docs/deployment_plan.md`
   - `docs/api.md`

3. Check service status and restart if needed:
   ```bash
   sudo systemctl status gunicorn-aqi
   sudo systemctl restart gunicorn-aqi
   ```

## Additional Resources

- Gunicorn documentation: https://docs.gunicorn.org/
- Systemd documentation: https://www.freedesktop.org/software/systemd/man/systemd.service.html
- Flask deployment: https://flask.palletsprojects.com/en/latest/deploying/
- Nginx reverse proxy: https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/

---

**Last Updated:** October 2, 2025  
**Server:** Ubuntu 20.04, 848MB RAM, Python 3.11, Flask + Gunicorn  
**Maintainer:** Air Quality Monitoring Team
