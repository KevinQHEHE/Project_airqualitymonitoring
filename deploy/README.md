# 🌟 Air Quality Monitoring System - Universal Deployment

## 🚀 One-Command Deployment for Any Ubuntu Server

This deployment package provides a **single script** that automatically installs and configures the complete Air Quality Monitoring System on any Ubuntu Linux server.

### ✨ Features
- **Zero-configuration deployment** - Just run one command
- **Automatic dependency installation** - Python, MongoDB, Nginx, etc.
- **Optimized for low-resource servers** - Works on 1GB RAM servers
- **Internet-ready** - Automatically configures firewall and Nginx
- **Auto-scaling workers** - Adjusts based on server resources  
- **Built-in health monitoring** - Automatic issue detection and fixing
- **Production-ready security** - Rate limiting, security headers, etc.

### 📋 Requirements
- Ubuntu Linux (any version from 18.04+)
- Sudo privileges
- Internet connection
- At least 1GB RAM recommended
- At least 5GB free disk space

## 🔥 Quick Start

### 1. Deploy the System
```bash
# Make the deployment script executable
chmod +x deploy/universal-deploy.sh

# Run the deployment (takes 5-10 minutes)
./deploy/universal-deploy.sh
```

That's it! The script will:
- Install all dependencies (Python, MongoDB, Nginx)
- Configure the database and web server
- Set up systemd services for auto-start
- Configure firewall for security
- Start all services
- Verify everything is working

### 2. Configure Your Settings (Optional)
```bash
# Edit the configuration file with your API keys
nano .env

# Restart services after configuration changes
./restart.sh
```

### 3. Access Your Application
- **Local**: http://localhost
- **Public**: http://YOUR_SERVER_IP

## 🛠️ Management Commands

After deployment, use these simple commands:

```bash
# Check system health and status
./deploy/health-check.sh

# Auto-fix any issues
./deploy/health-check.sh fix

# View system status
./status.sh

# Restart all services
./restart.sh

# View logs
./logs.sh

# Test all endpoints
./deploy/health-check.sh test
```

## 📊 System Services

The deployment creates these services:

| Service | Description | Port |
|---------|-------------|------|
| **air-quality-monitoring** | Main application | 8000 |
| **nginx** | Web server & proxy | 80 |
| **mongod** | MongoDB database | 27017 |

All services are automatically started and enabled for auto-start on boot.

## 🔧 Troubleshooting

### If something goes wrong:

1. **Check the health status:**
   ```bash
   ./deploy/health-check.sh
   ```

2. **Auto-fix common issues:**
   ```bash
   ./deploy/health-check.sh fix
   ```

3. **View detailed logs:**
   ```bash
   ./logs.sh
   ```

4. **Check service status:**
   ```bash
   sudo systemctl status air-quality-monitoring nginx mongod
   ```

5. **Restart everything:**
   ```bash
   ./restart.sh
   ```

### Common Issues & Solutions:

**🔸 Can't access from Internet:**
- Check if your cloud provider has security groups blocking port 80
- Verify firewall: `sudo ufw status`

**🔸 Service won't start:**
- Check logs: `sudo journalctl -u air-quality-monitoring -f`
- Run health check: `./deploy/health-check.sh fix`

**🔸 Database connection issues:**
- Ensure MongoDB is running: `sudo systemctl start mongod`
- Check MongoDB logs: `sudo journalctl -u mongod`

**🔸 Low memory issues:**
- The system auto-optimizes for low RAM
- Consider upgrading to at least 2GB RAM for better performance

## 🌐 Cloud Provider Setup

### AWS EC2:
1. Launch Ubuntu instance
2. Add security group rule: HTTP (80) from 0.0.0.0/0
3. Run deployment script

### Google Cloud Platform:
1. Create Ubuntu VM
2. Add firewall rule: `gcloud compute firewall-rules create allow-http --allow tcp:80`
3. Run deployment script

### DigitalOcean:
1. Create Ubuntu droplet
2. Firewall is usually open by default
3. Run deployment script

### Azure:
1. Create Ubuntu VM
2. Add network security group rule for port 80
3. Run deployment script

## 📁 File Structure

```
air-quality-monitoring/
├── deploy/
│   ├── universal-deploy.sh      # Main deployment script
│   ├── health-check.sh          # Health monitoring & auto-fix
│   └── README.md                # This file
├── backend/                     # Flask application
├── logs/                        # Application logs
├── venv/                        # Python virtual environment
├── .env                         # Configuration file
├── status.sh                    # Quick status check
├── restart.sh                   # Restart services
└── logs.sh                      # View logs
```

## ⚙️ Configuration Options

Edit `.env` file to customize:

```bash
# API Configuration
AQICN_API_KEY=your_api_key_here

# Database
MONGO_URI=mongodb://localhost:27017/air_quality_db

# Email Alerts (optional)
MAIL_SERVER=smtp.gmail.com
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password

# Features
SCHEDULER_ENABLED=true
BACKUP_ENABLED=true
ALERT_ENABLED=true
```

## 🔒 Security Features

- UFW firewall automatically configured
- Rate limiting on API endpoints  
- Security headers (XSS protection, etc.)
- MongoDB only accessible locally
- Non-root service execution
- Automatic SSL/HTTPS support (when configured)

## 📈 Performance Optimization

The system automatically optimizes based on server resources:

- **Low RAM (< 1GB)**: 1 worker, reduced connections
- **Normal RAM (1GB+)**: Multiple workers, full features
- **CPU cores**: Workers scale with available cores

## 🆘 Support

If you encounter issues:

1. Run the health check first: `./deploy/health-check.sh fix`
2. Check the deployment log: `cat deployment.log`
3. View service logs: `./logs.sh`

## 📝 Version Information

- **Compatible with**: Ubuntu 18.04, 20.04, 22.04, 24.04+
- **Python**: 3.8+
- **MongoDB**: 6.0+
- **Nginx**: Latest stable

---

## 🎯 Success Indicators

After deployment, you should see:

✅ All services running  
✅ Health check passing  
✅ Web interface accessible  
✅ API endpoints responding  
✅ Database connected  
✅ Firewall configured  

**Your Air Quality Monitoring System is ready to use!** 🌟