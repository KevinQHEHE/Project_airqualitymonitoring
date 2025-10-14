# Air Quality Monitoring System

A comprehensive web application for monitoring, analyzing, and forecasting air quality data with real-time updates, geospatial search, automated alerts, and interactive visualizations.

## Table of Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Architecture](#architecture)
4. [Technology Stack](#technology-stack)
5. [Project Structure](#project-structure)
6. [Prerequisites](#prerequisites)
7. [Installation](#installation)
8. [Configuration](#configuration)
9. [Running the Application](#running-the-application)
10. [Data Ingestion](#data-ingestion)
11. [API Documentation](#api-documentation)
12. [Database Schema](#database-schema)
13. [Background Tasks](#background-tasks)
14. [Backup and Recovery](#backup-and-recovery)
15. [Testing](#testing)
16. [Deployment](#deployment)
17. [Monitoring and Maintenance](#monitoring-and-maintenance)
18. [Contributing](#contributing)
19. [License](#license)

## Overview

The Air Quality Monitoring System is a production-ready Flask application that collects air quality data from the World Air Quality Index (WAQI) API, stores it in MongoDB, and provides a REST API and web dashboard for real-time monitoring and analysis. The system monitors key pollutants including PM2.5, PM10, O3, NO2, SO2, and CO, calculating overall Air Quality Index (AQI) values with health recommendations.

### Key Capabilities

- Real-time air quality data ingestion from WAQI API
- Geospatial search to find nearest monitoring stations
- Historical trend analysis and forecasting
- Automated email alerts for hazardous air quality levels
- Interactive maps with color-coded AQI markers
- PDF report generation for authorities and research
- Role-based access control with JWT authentication
- Automated database backups with point-in-time recovery

## Features

### Core Features

- **Real-time Monitoring**: Continuous data collection with updates every 1-24 hours (configurable)
- **Geospatial Search**: Find nearest monitoring stations using MongoDB 2dsphere indexes
- **Interactive Dashboard**: Real-time charts and maps using Chart.js and Leaflet
- **Historical Analysis**: Query and visualize air quality trends over time
- **Alert System**: Email notifications when AQI exceeds configurable thresholds
- **Forecasting**: Daily air quality forecasts using statistical models
- **Report Export**: Generate PDF reports with charts and analysis
- **User Management**: Registration, authentication, and role-based access (public, admin)

### API Features

- RESTful endpoints for stations, readings, forecasts, and alerts
- JWT-based authentication with refresh tokens
- Rate limiting with Redis or in-memory storage
- Response caching for performance optimization
- Comprehensive error handling and validation
- Health check endpoints for monitoring

## Architecture

The system follows a clean architecture pattern with clear separation of concerns:

```
Presentation Layer (Flask Blueprints)
         |
Business Logic Layer (Services)
         |
Data Access Layer (Repositories)
         |
Database Layer (MongoDB)
```

### Key Components

- **Flask Application**: WSGI application with modular blueprints
- **MongoDB Database**: Document storage with time-series optimization
- **WAQI Client**: HTTP client for external API integration
- **Data Ingestion Scheduler**: APScheduler for periodic data collection
- **Backup Scheduler**: Automated database backups with retention policies
- **Cache Layer**: Response caching to reduce database load

## Technology Stack

### Backend

- **Python**: 3.8 or higher
- **Flask**: 2.3.0+ (Web framework)
- **PyMongo**: 4.5.0+ (MongoDB driver)
- **Pydantic**: 2.0.0+ (Data validation)
- **APScheduler**: 3.10.0+ (Task scheduling)
- **Flask-JWT-Extended**: 4.6.0+ (JWT authentication)
- **Flask-Mail**: 0.9.1+ (Email notifications)
- **Flask-Limiter**: 3.0.0+ (Rate limiting)
- **Gunicorn**: 21.0.0+ (Production WSGI server)

### Data Processing

- **Pandas**: 2.0.0+ (Data manipulation)
- **NumPy**: 1.24.0+ (Numerical computing)
- **scikit-learn**: 1.3.0+ (Machine learning for forecasting)

### Frontend

- **Jinja2**: 3.1.0+ (Template engine)
- **Bootstrap**: 5.x (CSS framework, CDN)
- **Chart.js**: 4.x (Data visualization, CDN)
- **Leaflet**: 1.9.x (Interactive maps, CDN)

### Database

- **MongoDB**: 4.4+ or MongoDB Atlas (Cloud database)
- Time-series collections for efficient storage
- 2dsphere geospatial indexes
- TTL indexes for automatic data expiration

### External Services

- **WAQI API**: World Air Quality Index data platform
- **Email Server**: SMTP for alert notifications

## Project Structure

```
air-quality-monitoring/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── wsgi.py                           # WSGI entry point
├── .env.sample                       # Environment variables template
├── backend/                          # Flask application
│   └── app/
│       ├── __init__.py              # Application factory
│       ├── config.py                # Configuration management
│       ├── db.py                    # MongoDB connection and utilities
│       ├── extensions.py            # Flask extensions initialization
│       ├── repositories.py          # Data access layer
│       ├── blueprints/              # Route handlers
│       │   ├── api/                # API endpoints
│       │   │   ├── admin/          # Admin management
│       │   │   ├── air_quality/    # Air quality data
│       │   │   ├── alerts/         # Alert management
│       │   │   ├── auth/           # Authentication
│       │   │   ├── forecasts/      # Forecast data
│       │   │   ├── stations/       # Station management
│       │   │   └── subscriptions/  # Alert subscriptions
│       │   └── web/                # Web interface
│       ├── middleware/              # Custom middleware
│       │   └── admin_required.py   # Admin authorization
│       ├── schemas/                 # Data validation schemas
│       │   ├── mongo_validators/   # MongoDB JSON schemas
│       │   └── schemas_jsonschema/ # Pydantic schemas
│       ├── services/                # Business logic
│       │   ├── admin/              # Admin services
│       │   ├── auth/               # Authentication services
│       │   └── forecasting/        # Forecasting algorithms
│       ├── tasks/                   # Background tasks
│       │   └── alerts.py           # Alert processing
│       ├── templates/               # Jinja2 templates
│       │   ├── admin/              # Admin interface
│       │   ├── auth/               # Login/register
│       │   ├── dashboard/          # Dashboard views
│       │   └── email/              # Email templates
│       └── static/                  # Static assets
│           └── js/                 # JavaScript files
├── ingest/                          # Data ingestion modules
│   ├── aqicn_client.py             # WAQI API client
│   ├── get_station_reading.py      # Station data ingestion
│   ├── get_forecast_data.py        # Forecast ingestion
│   ├── import_vietnam_stations.py  # Station initialization
│   ├── streaming.py                # Ingestion scheduler
│   ├── mongo_utils.py              # MongoDB utilities
│   └── catchup.py                  # Historical data backfill
├── backup_dtb/                      # Database backup system
│   ├── backup_data.py              # Backup implementation
│   ├── rollback_data.py            # Restore functionality
│   └── scheduler.py                # Backup scheduler
├── scripts/                         # Utility scripts
│   ├── run_monitor.py              # Monitoring script
│   └── inspect_tar.py              # Backup inspection
├── scripts_test/                    # Test scripts
│   ├── test_db_connection.py       # Database tests
│   ├── test_stations_api.py        # API tests
│   └── test_nearest_integration.py # Integration tests
├── docs/                            # Documentation
│   ├── api.md                      # API reference
│   ├── architecture.md             # Architecture overview
│   ├── db_schema.md                # Database schema
│   ├── db_setup.md                 # Database setup guide
│   ├── indexes.md                  # Index documentation
│   ├── backup_rollback_db.md       # Backup guide
│   ├── requirements-moscow-v1.md   # Requirements specification
│   ├── plantuml/                   # Architecture diagrams
│   ├── postman/                    # API collection
│   └── schema/                     # Schema diagrams
├── config/                          # Configuration files
│   └── disposable_domains.txt      # Email validation
└── deploy/                          # Deployment scripts
    ├── deploy.sh                   # Production deployment
    ├── health_check.sh             # Health monitoring
    └── README-DEPLOY.md            # Deployment guide
```

## Prerequisites

### System Requirements

- Python 3.8 or higher
- MongoDB 4.4 or higher (or MongoDB Atlas account)
- 2GB RAM minimum (4GB recommended)
- 10GB disk space for data storage

### Required Accounts

- **WAQI API Token**: Register at https://aqicn.org/data-platform/token/
- **MongoDB**: Local installation or Atlas cluster
- **SMTP Server**: For email alerts (Gmail, SendGrid, etc.)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/xuanquangIT/air-quality-monitoring.git
cd air-quality-monitoring
```

### 2. Create Virtual Environment

On Linux/macOS:
```bash
python3 -m venv venv
source venv/bin/activate
```

On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Setup MongoDB

Option A: MongoDB Atlas (Cloud)
1. Create free cluster at https://www.mongodb.com/cloud/atlas
2. Create database user
3. Whitelist IP addresses
4. Get connection string

Option B: Local MongoDB
```bash
# Install MongoDB Community Edition
# See: https://docs.mongodb.com/manual/installation/

# Start MongoDB service
sudo systemctl start mongod  # Linux
brew services start mongodb-community  # macOS
```

### 5. Configure Environment Variables

```bash
cp .env.sample .env
```

Edit `.env` file with your configuration (see [Configuration](#configuration) section).

### 6. Initialize Database

```bash
# Import initial stations data
python ingest/import_vietnam_stations.py

# Create indexes
python -c "from backend.app import create_app; from backend.app import db; app = create_app(); app.app_context().push(); db.ensure_indexes()"
```

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```bash
# Flask Configuration
SECRET_KEY=your-secret-key-change-in-production
FLASK_ENV=development

# JWT Configuration
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ACCESS_TOKEN_EXPIRES=3600
JWT_REFRESH_TOKEN_EXPIRES=604800

# MongoDB Configuration
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/
MONGO_DB=air_quality_monitoring

# WAQI API Configuration
WAQI_API_KEY=your-waqi-api-token
WAQI_API_URL=https://api.waqi.info

# Email Configuration (for alerts)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Data Ingestion Configuration
STATION_POLLING_INTERVAL_MINUTES=1440  # 24 hours
FORECAST_POLLING_INTERVAL_MINUTES=1440  # 24 hours

# Backup Configuration
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_DAYS=14

# Rate Limiting
RATELIMIT_STORAGE_URL=memory://
# For production with Redis:
# RATELIMIT_STORAGE_URL=redis://localhost:6379/0

# Cache Configuration
CACHE_TYPE=simple
CACHE_DEFAULT_TIMEOUT=300
```

### Configuration Details

- **SECRET_KEY**: Flask session encryption (generate with `python -c "import secrets; print(secrets.token_hex(32))"`)
- **JWT_SECRET_KEY**: JWT token signing (use different key from SECRET_KEY)
- **MONGO_URI**: MongoDB connection string (include username, password, and database)
- **WAQI_API_KEY**: Required for data ingestion (get from https://aqicn.org/data-platform/token/)
- **MAIL_***: SMTP configuration for email alerts (use app passwords for Gmail)
- **STATION_POLLING_INTERVAL_MINUTES**: How often to fetch new readings (default: 1440 = 24 hours)
- **BACKUP_INTERVAL_HOURS**: Database backup frequency (default: 24 hours)

## Running the Application

### Development Mode

```bash
# Activate virtual environment
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\Activate.ps1  # Windows

# Run Flask development server
python wsgi.py
```

The application will be available at http://localhost:5000

### Production Mode

```bash
# Using Gunicorn (Linux/macOS only)
gunicorn wsgi:app -w 4 -b 0.0.0.0:8000 --timeout 120

# Using deployment script
./deploy/deploy.sh deploy
```

For Windows production, use waitress:
```bash
pip install waitress
waitress-serve --host=0.0.0.0 --port=8000 wsgi:app
```

### Health Check

Verify the application is running:

```bash
curl http://localhost:5000/api/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "air-quality-monitoring-api",
  "database": {
    "status": "healthy",
    "ping_ms": 5
  }
}
```

## Data Ingestion

### Initial Station Import

Import monitoring stations from WAQI API:

```bash
python ingest/import_vietnam_stations.py
```

### Manual Data Collection

Fetch current readings for all stations:

```bash
# Dry run (preview without saving)
python ingest/get_station_reading.py --dry-run

# Actual ingestion
python ingest/get_station_reading.py
```

Fetch daily forecasts:

```bash
python ingest/get_forecast_data.py
```

### Automated Ingestion

The application automatically starts background schedulers when running:

- **Station Readings**: Polls every 24 hours (configurable via `STATION_POLLING_INTERVAL_MINUTES`)
- **Forecasts**: Polls every 24 hours (configurable via `FORECAST_POLLING_INTERVAL_MINUTES`)

View scheduler status in application logs.

### Historical Data Backfill

To backfill historical data:

```bash
python ingest/catchup.py --start-date 2024-01-01 --end-date 2024-12-31
```

## API Documentation

### Authentication

#### Register User
```http
POST /api/auth/register
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123",
  "username": "john_doe"
}
```

#### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePassword123"
}
```

Response:
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

### Stations

#### Get Nearest Station
```http
GET /api/stations/nearest?lat=21.0285&lng=105.8542&radius=25&limit=5
```

Response:
```json
{
  "stations": [
    {
      "station_id": "1583",
      "name": "Hanoi, Vietnam",
      "location": {
        "type": "Point",
        "coordinates": [105.8542, 21.0285]
      },
      "_distance_km": 0.5,
      "latest_reading": {
        "aqi": 95,
        "iaqi": {
          "pm25": {"v": 95},
          "pm10": {"v": 75}
        },
        "time": {
          "iso": "2024-12-07T15:00:00+07:00"
        }
      }
    }
  ]
}
```

#### List All Stations
```http
GET /api/stations?page=1&page_size=20
```

### Air Quality Data

#### Get Station Readings
```http
GET /api/air-quality/readings?station_id=1583&start_date=2024-12-01&end_date=2024-12-07
```

#### Get Latest Reading
```http
GET /api/air-quality/latest?station_id=1583
```

### Forecasts

#### Get Daily Forecast
```http
GET /api/forecasts/daily?station_id=1583&date=2024-12-07
```

### Alerts

#### Create Alert Subscription
```http
POST /api/subscriptions
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "station_id": "1583",
  "threshold": 150,
  "email": "user@example.com"
}
```

For complete API documentation, see `docs/api.md`.

## Database Schema

### Collections

#### waqi_stations
Stores monitoring station metadata and location:

```json
{
  "_id": 1583,
  "city": {
    "name": "Hanoi, Vietnam",
    "url": "https://aqicn.org/city/vietnam/hanoi/",
    "geo": {
      "type": "Point",
      "coordinates": [105.8542, 21.0285]
    }
  },
  "time": {"tz": "+07:00"},
  "attributions": [...]
}
```

#### waqi_station_readings
Time-series collection for air quality measurements:

```json
{
  "ts": "2024-12-07T08:00:00.000Z",
  "meta": {"station_idx": 1583},
  "aqi": 95,
  "time": {
    "v": 1701939600,
    "s": "2024-12-07 15:00:00",
    "tz": "+07:00"
  },
  "iaqi": {
    "pm25": {"v": 95},
    "pm10": {"v": 75},
    "o3": {"v": 42}
  }
}
```

#### waqi_daily_forecasts
Daily air quality forecasts by pollutant:

```json
{
  "station_idx": 1583,
  "forecast_date": "2024-12-08",
  "pollutant": "pm25",
  "avg": 85,
  "min": 70,
  "max": 100,
  "day": [75, 80, 85, 90, 95, 100, 95, 90]
}
```

#### users
User accounts and authentication:

```json
{
  "_id": ObjectId("..."),
  "email": "user@example.com",
  "username": "john_doe",
  "password_hash": "...",
  "role": "public",
  "created_at": "2024-12-07T10:00:00.000Z"
}
```

For complete schema documentation, see `docs/db_schema.md`.

## Background Tasks

### Data Ingestion Scheduler

Automatically runs in the application process:

- Fetches latest readings from all stations
- Fetches daily forecasts
- Configurable via environment variables
- Uses checkpoints to avoid duplicate data

### Alert Processor

Monitors air quality levels and sends email alerts:

- Checks readings against user-defined thresholds
- Sends email notifications via SMTP
- Configurable alert templates

### Cache Maintenance

- Response caching with 5-minute TTL
- Automatic cache invalidation on new data
- TTL indexes for automatic cleanup

## Backup and Recovery

### Automated Backups

The backup scheduler runs automatically:

```python
# Configuration in .env
BACKUP_INTERVAL_HOURS=24
BACKUP_RETENTION_DAYS=14
```

Backups are stored in `backup_dtb/backup_data/` with format:
```
backup_YYYYMMDD_HHMMSS.tar.gz
```

### Manual Backup

```bash
python backup_dtb/backup_data.py
```

### Restore from Backup

```bash
python backup_dtb/rollback_data.py backup_dtb/backup_data/backup_20241207_100000.tar.gz
```

For detailed backup documentation, see `docs/backup_rollback_db.md`.

## Testing

### Run All Tests

```bash
pytest
```

### Test Database Connection

```bash
python scripts_test/test_db_connection.py
```

### Test API Endpoints

```bash
python scripts_test/test_stations_api.py
```

### Integration Tests

```bash
python scripts_test/test_nearest_integration.py
```

### Using Postman

Import collections from `docs/postman/`:
- `auth.postman_collection.json` - Authentication endpoints
- `get-stations.postman_collection.json` - Station queries
- `forecast-weekly.postman_collection.json` - Forecast endpoints

## Deployment

### Production Deployment

1. **Prepare Server**
   - Ubuntu 20.04+ or similar Linux distribution
   - Install Python 3.8+, MongoDB, Nginx
   - Configure firewall (allow ports 80, 443)

2. **Deploy Application**
   ```bash
   ./deploy/deploy.sh deploy
   ```

3. **Configure Nginx**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

4. **Setup SSL Certificate**
   ```bash
   sudo certbot --nginx -d your-domain.com
   ```

5. **Configure Systemd Service**
   ```bash
   sudo systemctl enable air-quality-monitoring
   sudo systemctl start air-quality-monitoring
   ```

For complete deployment guide, see `deploy/README-DEPLOY.md`.

## Monitoring and Maintenance

### Health Checks

```bash
# Application health
curl http://localhost:5000/api/health

# Database health
./deploy/health_check.sh
```

### Log Monitoring

Application logs include:
- Request/response logs
- Data ingestion status
- Error traces
- Background task execution

### Performance Monitoring

Key metrics to monitor:
- API response times
- Database query performance
- Cache hit rates
- Background task execution times
- Error rates

### Database Indexes

Verify indexes are created:

```bash
python -c "from backend.app import create_app; from backend.app import db; app = create_app(); app.app_context().push(); db.ensure_indexes()"
```

See `docs/indexes.md` for index documentation.

## Contributing

### Development Workflow

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make changes following the code style
4. Add tests for new functionality
5. Ensure all tests pass (`pytest`)
6. Commit changes (`git commit -m 'Add amazing feature'`)
7. Push to branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Code Style

- Follow PEP 8 for Python code
- Use type hints for function signatures
- Add docstrings for modules, classes, and functions
- Keep functions focused and testable
- Use meaningful variable names

### Testing Requirements

- Write unit tests for business logic
- Add integration tests for API endpoints
- Ensure test coverage above 80%
- Test edge cases and error conditions

## License

This project is developed for educational purposes as part of the Advanced Database course at University.
