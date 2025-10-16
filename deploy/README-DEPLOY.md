# Báo Cáo Triển Khai Hệ Thống Air Quality Monitoring trên Azure

## 1. Tổng Quan Hệ Thống

**Ứng dụng:** Air Quality Monitoring - Hệ thống giám sát chất lượng không khí  
**Nền tảng triển khai:** Microsoft Azure Virtual Machine  
**Hệ điều hành:** Ubuntu 20.04 LTS  
**Công nghệ:** Python 3.11, Flask, Gunicorn, Nginx, MongoDB Atlas  
**Domain:** https://airqualitymonitor.page

## 2. Kiến Trúc Triển Khai

### 2.1. Cấu Trúc Hệ Thống

```
Internet (HTTPS)
      ↓
Azure VM (Ubuntu 20.04)
      ↓
Nginx (Reverse Proxy, Port 80/443)
      ↓
Gunicorn (WSGI Server, Port 8000)
      ↓
Flask Application
      ↓
MongoDB Atlas (Cloud Database)
```

### 2.2. Thông Số Máy Chủ

- **Loại VM:** Azure Standard B1s
- **RAM:** 848MB
- **vCPU:** 1 core
- **Storage:** 30GB SSD
- **IP Public:** Được cấp phát từ Azure
- **Firewall:** Azure Network Security Group (NSG)

### 2.3. Cấu Hình Gunicorn

```ini
Workers: 2                          # Tối ưu cho 848MB RAM
Threads per worker: 2               # Tổng 4 threads
Worker class: sync                  # Synchronous workers
Timeout: 300s                       # 5 phút cho long-running requests
Max requests: 1000                  # Worker recycling
Max requests jitter: 50             # Random jitter
```

**Lý do lựa chọn:**
- 2 workers phù hợp với RAM hạn chế (công thức: 2 * CPU + 1, nhưng giới hạn bởi RAM)
- Sync workers tiết kiệm bộ nhớ hơn async cho workload này
- Timeout cao để xử lý data ingest và API calls tới external services
- Worker recycling ngăn memory leaks tích lũy

## 3. Quy Trình Triển Khai

### 3.1. Chuẩn Bị Môi Trường

**Bước 1: Tạo Azure VM**
```bash
# Tạo Resource Group
az group create --name aqi-monitoring-rg --location southeastasia

# Tạo VM Ubuntu
az vm create \
  --resource-group aqi-monitoring-rg \
  --name aqi-monitoring-vm \
  --image Ubuntu2004 \
  --size Standard_B1s \
  --admin-username azureuser \
  --generate-ssh-keys
```

**Bước 2: Cấu Hình Network Security Group**
```bash
# Mở port 80 (HTTP)
az vm open-port --port 80 --resource-group aqi-monitoring-rg --name aqi-monitoring-vm

# Mở port 443 (HTTPS)
az vm open-port --port 443 --resource-group aqi-monitoring-rg --name aqi-monitoring-vm --priority 1001
```

**Bước 3: Cài Đặt Phần Mềm Cơ Bản**
```bash
# SSH vào VM
ssh azureuser@<vm-public-ip>

# Update system
sudo apt update && sudo apt upgrade -y

# Cài đặt Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Cài đặt Git
sudo apt install -y git

# Cài đặt Nginx
sudo apt install -y nginx
```

### 3.2. Triển Khai Ứng Dụng

**Bước 1: Clone Repository**
```bash
cd /home/azureuser
git clone https://github.com/xuanquangIT/air-quality-monitoring.git
cd air-quality-monitoring
```

**Bước 2: Cấu Hình Biến Môi Trường**
```bash
# Tạo file .env
cp .env.example .env
nano .env
```

Nội dung file `.env`:
```env
# Server Configuration
SERVICE_USER=azureuser
PROJECT_DIR=/home/azureuser/air-quality-monitoring
SERVICE_PORT=8000
NGINX_PORT=80

# Git Configuration
GIT_REMOTE=origin
GIT_BRANCH=main

# Domain Configuration
PRIMARY_DOMAIN=airqualitymonitor.page
PUBLIC_URL=https://airqualitymonitor.page

# MongoDB Atlas
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/aqi_db

# Application Settings
FLASK_ENV=production
SECRET_KEY=<random-secret-key>
API_TOKEN=<aqicn-api-token>
```

**Bước 3: Cấu Hình Nginx**
```bash
sudo nano /etc/nginx/sites-available/aqi-monitoring
```

Nội dung cấu hình Nginx:
```nginx
server {
    listen 80;
    server_name airqualitymonitor.page www.airqualitymonitor.page;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/aqi-monitoring /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

**Bước 4: Chạy Deployment Script**
```bash
# Cấp quyền thực thi
chmod +x deploy/deploy.sh deploy/health_check.sh

# Chạy deployment
./deploy/deploy.sh
```

### 3.3. Kiểm Tra Triển Khai

**Kiểm tra Health Check:**
```bash
./deploy/health_check.sh --verbose
```

**Kiểm tra Service Status:**
```bash
sudo systemctl status gunicorn-aqi
```

**Xem Logs:**
```bash
# Systemd logs
sudo journalctl -u gunicorn-aqi -f

# Application logs
tail -f logs/gunicorn-error.log logs/gunicorn-access.log
```

## 4. Tính Năng Deployment System

### 4.1. Automated Deployment Script (`deploy.sh`)

**Chức năng tự động:**
1. ✅ Pull code mới nhất từ Git
2. ✅ Tạo backup trước khi deploy
3. ✅ Cài đặt/cập nhật dependencies
4. ✅ Cấu hình systemd service
5. ✅ Restart Gunicorn service
6. ✅ Reload Nginx

**Sử dụng:**
```bash
# Deployment tiêu chuẩn
./deploy/deploy.sh

# Bỏ qua backup (nhanh hơn)
./deploy/deploy.sh --skip-backup

# Bỏ qua git pull (test local changes)
./deploy/deploy.sh --skip-pull
```

### 4.2. Health Check Script (`health_check.sh`)

**12 kiểm tra tự động:**
1. Systemd service status
2. Port binding (service listening)
3. Gunicorn processes
4. HTTP endpoint responsiveness
5. Database connectivity
6. Disk space
7. Memory usage
8. Recent error logs
9. Nginx status
10. Public URL accessibility
11. Service stability
12. Process resource usage

**Exit codes:**
- `0`: Healthy (tất cả kiểm tra passed)
- `1`: Minor issues (cần điều tra)
- `2`: Critical issues (cần xử lý ngay)

### 4.3. Systemd Service Management

**Service name:** `gunicorn-aqi`

**Quản lý service:**
```bash
# Start
sudo systemctl start gunicorn-aqi

# Stop
sudo systemctl stop gunicorn-aqi

# Restart
sudo systemctl restart gunicorn-aqi

# Reload (graceful restart)
sudo systemctl reload gunicorn-aqi

# Status
sudo systemctl status gunicorn-aqi

# Enable on boot
sudo systemctl enable gunicorn-aqi
```

## 5. Bảo Mật

### 5.1. Network Security

- **Firewall:** Azure NSG chỉ mở port 80, 443, 22
- **SSH:** Chỉ cho phép SSH key authentication
- **HTTPS:** SSL/TLS certificate từ Let's Encrypt (tự động gia hạn)
- **MongoDB:** Connection string lưu trong `.env`, không commit vào Git

### 5.2. Application Security

- Service chạy với user `azureuser` (non-root)
- Environment variables load từ `.env` (không expose)
- Logs không chứa sensitive data
- Nginx reverse proxy che giấu Gunicorn port internal

### 5.3. Secrets Management

- MongoDB URI, API tokens lưu trong `.env`
- `.env` file có permission 600 (chỉ owner đọc/ghi)
- Không commit `.env` vào Git (có `.gitignore`)

## 6. Backup & Rollback

### 6.1. Automatic Backup

Mỗi lần deploy, script tự động tạo backup:
```bash
deploy_backups/
├── backup_20250107_140000.tar.gz
├── backup_20250107_150000.tar.gz
└── backup_20250107_160000.tar.gz
```

- Giữ 5 bản backup gần nhất
- Exclude: `venv/`, `__pycache__/`, `.git/`

### 6.2. Rollback Process

```bash
# Stop service
sudo systemctl stop gunicorn-aqi

# Extract backup
tar -xzf deploy_backups/backup_YYYYMMDD_HHMMSS.tar.gz

# Restart service
sudo systemctl start gunicorn-aqi

# Verify
./deploy/health_check.sh
```

### 6.3. Database Backup

- MongoDB Atlas tự động backup (Point-in-Time Recovery)
- Snapshot schedule: Daily
- Retention: 7 days

## 7. Monitoring & Logging

### 7.1. Application Logs

**Vị trí logs:**
```
logs/
├── gunicorn-access.log    # HTTP requests
└── gunicorn-error.log     # Errors, exceptions
```

**Xem logs realtime:**
```bash
tail -f logs/gunicorn-error.log logs/gunicorn-access.log
```

### 7.2. System Logs

**Systemd journal:**
```bash
# Xem logs gần nhất
sudo journalctl -u gunicorn-aqi -n 100

# Follow logs
sudo journalctl -u gunicorn-aqi -f

# Logs trong 1 giờ qua
sudo journalctl -u gunicorn-aqi --since "1 hour ago"
```

### 7.3. Automated Monitoring

**Cron job health check (mỗi 5 phút):**
```bash
crontab -e

# Thêm dòng:
*/5 * * * * /home/azureuser/air-quality-monitoring/deploy/health_check.sh >> /home/azureuser/health-check.log 2>&1
```

## 8. Performance & Optimization

### 8.1. Gunicorn Workers Tuning

**Công thức tính workers:**
```
workers = (2 * CPU_cores) + 1
```

Với VM hiện tại (1 vCPU, 848MB RAM):
- Workers: 2 (giới hạn bởi RAM)
- Threads: 2 per worker
- Total concurrent requests: 4

### 8.2. Memory Optimization

- Sử dụng sync workers (tiết kiệm RAM)
- Worker recycling sau 1000 requests (ngăn memory leaks)
- Không chạy background tasks nặng trên VM

### 8.3. Database Optimization

- MongoDB Atlas connection pooling
- Index trên các trường query thường xuyên
- Query projection (chỉ lấy fields cần thiết)

## 9. Troubleshooting

### 9.1. Service Không Start

**Kiểm tra:**
```bash
# Service status
sudo systemctl status gunicorn-aqi

# Logs chi tiết
sudo journalctl -u gunicorn-aqi -n 50

# Error log
tail -n 50 logs/gunicorn-error.log

# Test manual
source venv/bin/activate
gunicorn backend.app.wsgi:app --bind 0.0.0.0:8000
```

### 9.2. Port Đã Được Sử dụng

**Xử lý:**
```bash
# Tìm process sử dụng port
sudo ss -tlnp | grep :8000

# Stop service
sudo systemctl stop gunicorn-aqi

# Kill leftover processes
sudo pkill -f 'gunicorn.*backend.app.wsgi'

# Start lại
sudo systemctl start gunicorn-aqi
```

### 9.3. Database Connection Error

**Kiểm tra:**
```bash
# Kiểm tra MONGO_URI trong .env
cat .env | grep MONGO_URI

# Test connection từ Python
python3 -c "from backend.app.db import test_connection; test_connection()"

# Ping MongoDB Atlas
ping <cluster-hostname>
```

### 9.4. High Memory Usage

**Giải pháp:**
```bash
# Giảm workers
sudo systemctl edit gunicorn-aqi

# Thêm override:
[Service]
ExecStart=
ExecStart=/home/azureuser/air-quality-monitoring/venv/bin/gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 1 \
    backend.app.wsgi:app

# Reload và restart
sudo systemctl daemon-reload
sudo systemctl restart gunicorn-aqi
```

## 10. Chi Phí & Tối Ưu

### 10.1. Chi Phí Azure VM

**Ước tính hàng tháng (Standard B1s):**
- VM: ~$8-10 USD/tháng
- Storage: ~$1-2 USD/tháng
- Network egress: ~$1-3 USD/tháng (tùy traffic)
- **Tổng:** ~$10-15 USD/tháng

### 10.2. Chi Phí MongoDB Atlas

- Free tier: M0 (512MB storage, shared cluster)
- Phù hợp cho development/small production
- Upgrade: M10+ khi cần scale (~$57/month)

### 10.3. Tối Ưu Chi Phí

- Sử dụng Azure Reserved Instances (giảm 40-60% nếu commit 1-3 năm)
- Schedule VM shutdown ngoài giờ peak (nếu không cần 24/7)
- Sử dụng Azure CDN cho static assets
- Monitor bandwidth usage, tối ưu API responses

## 11. Kết Luận

### 11.1. Ưu Điểm Giải Pháp

✅ **Đơn giản:** Deployment tự động với 1 lệnh  
✅ **Ổn định:** Systemd quản lý service, auto-restart on failure  
✅ **An toàn:** Automatic backups, easy rollback  
✅ **Giám sát:** Comprehensive health checks, detailed logging  
✅ **Chi phí thấp:** Phù hợp với budget hạn chế ($10-15/month)  
✅ **Scalable:** Dễ dàng upgrade VM size khi cần  

### 11.2. Hạn Chế

⚠️ **Single point of failure:** Chỉ có 1 VM, không high availability  
⚠️ **Limited resources:** 848MB RAM giới hạn concurrent requests  
⚠️ **Manual scaling:** Cần manual intervention để scale up/out  

### 11.3. Khuyến Nghị Nâng Cấp Tương Lai

**Khi traffic tăng:**
1. Upgrade VM size (B2s: 2vCPU, 4GB RAM)
2. Add Azure Load Balancer + multiple VMs
3. Migrate to Azure App Service for Containers (PaaS)
4. Implement Azure Application Insights cho monitoring nâng cao
5. Setup Azure CDN cho static content
6. Consider Azure Kubernetes Service (AKS) cho container orchestration

**Database scaling:**
1. Upgrade MongoDB Atlas tier (M10+)
2. Enable MongoDB Atlas Global Clusters cho multi-region
3. Implement read replicas
4. Consider Azure Cosmos DB for MongoDB API (native Azure integration)

## 12. Tài Liệu Tham Khảo

### 12.1. Deployment Scripts

- `deploy/deploy.sh` - Main deployment script
- `deploy/health_check.sh` - Health check script
- `deploy/README.md` - Detailed deployment documentation

### 12.2. External Resources

- **Gunicorn:** https://docs.gunicorn.org/
- **Systemd:** https://www.freedesktop.org/software/systemd/man/systemd.service.html
- **Nginx:** https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/
- **Azure VM:** https://docs.microsoft.com/en-us/azure/virtual-machines/
- **MongoDB Atlas:** https://docs.atlas.mongodb.com/

---

**Ngày cập nhật:** 7 tháng 10, 2025  
**Phiên bản hệ thống:** Ubuntu 20.04, Python 3.11, Flask + Gunicorn  
**Người bảo trì:** Air Quality Monitoring Team
