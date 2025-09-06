# Air Quality Monitoring System

A comprehensive air quality monitoring system that ingests data from OpenAQ API, provides real-time analytics, forecasting, and alert capabilities through a REST API and interactive dashboard.

## Project Structure

```
air-quality-monitoring/
├─ README.md                           # Project documentation and setup guide
├─ .gitignore                          # Git ignore rules for Python and development files
├─ .env.sample                         # Environment variables template (MongoDB, email, API keys)
├─ pyproject.toml                      # Python dependencies and development tools configuration
├─ config/
│  └─ locations.yaml                   # List of cities with coordinates for data ingestion
├─ docs/
│  ├─ architecture.md                  # High-level system architecture diagram and overview
│  ├─ api.md                           # Complete REST API endpoint documentation
│  └─ db_schema.md                     # MongoDB collections schema and index definitions
├─ backend/
│  └─ app/
│     ├─ config.py                     # Configuration management and environment variable loading
│     ├─ extensions.py                 # Flask extensions initialization (PyMongo, Mail, Limiter, Login, Cache)
│     ├─ wsgi.py                       # WSGI entrypoint for development and production deployment
│     ├─ blueprints/                   # Flask blueprints for modular route organization
│     │  ├─ auth/
│     │  │  └─ routes.py               # User authentication and authorization endpoints
│     │  ├─ stations/
│     │  │  └─ routes.py               # Monitoring station CRUD operations
│     │  ├─ measurements/
│     │  │  └─ routes.py               # Air quality measurement data queries and CSV import
│     │  ├─ aggregates/
│     │  │  └─ routes.py               # Data analytics and aggregation endpoints
│     │  ├─ alerts/
│     │  │  └─ routes.py               # Alert subscription and management endpoints
│     │  ├─ forecasts/
│     │  │  └─ routes.py               # Air quality prediction services
│     │  ├─ exports/
│     │  │  └─ routes.py               # Data export functionality (CSV/PDF)
│     │  ├─ realtime/
│     │  │  └─ sse.py                  # Server-Sent Events for real-time dashboard updates
│     │  └─ dashboard/
│     │     └─ routes.py               # Web dashboard interface with charts and maps
│     ├─ services/                     # Business logic layer (framework-agnostic)
│     ├─ repositories/                 # Data access layer with MongoDB operations
│     ├─ schemas/                      # Pydantic models for request/response validation
│     ├─ tasks/                        # Background job scheduling with APScheduler
│     ├─ utils/                        # Shared utility functions and helpers
│     ├─ templates/                    # Jinja2 templates for web interface
│     │  ├─ layout.html                # Base template with navigation and common elements
│     │  ├─ dashboard/
│     │  │  └─ index.html              # Interactive dashboard with Chart.js and Leaflet maps
│     │  ├─ auth/
│     │  │  ├─ login.html              # User login form
│     │  │  └─ register.html           # User registration form
│     │  └─ reports/
│     │     └─ summary.html            # Air quality summary report template
│     └─ static/                       # Static web assets (CSS, JavaScript)
│        └─ js/
│           └─ dashboard.js            # Frontend JavaScript for API calls and chart rendering
├─ ingest/
│  └─ __init__.py                      # External data ingestion module for OpenAQ API
├─ scripts/                            # Database and development utility scripts (empty)
├─ tests/                              # Test suite directory (empty)
└─ .github/
   └─ workflows/
      └─ ci.yml                        # GitHub Actions CI/CD pipeline configuration
```

## Current Development Status

This project structure provides the foundation for a comprehensive air quality monitoring system. The current implementation includes:

### ✅ Completed Structure
- **Core Configuration**: Environment setup, Python dependencies, and project configuration
- **Flask Application Framework**: Basic Flask app structure with blueprints for modular development
- **API Route Blueprints**: Organized endpoints for authentication, stations, measurements, aggregates, alerts, forecasts, exports, and real-time features
- **Template System**: Jinja2 templates for dashboard, authentication, and reporting
- **Documentation**: API documentation and database schema planning
- **CI/CD Pipeline**: GitHub Actions workflow for automated testing and deployment
- **Database Setup**: MongoDB connection configuration and index creation
- **Connection Testing**: MongoDB connection verification utility

### 🚧 To Be Implemented
The following components are structured but need implementation:
- **Business Logic**: Service layer implementations for each feature
- **Data Access**: Repository layer with MongoDB operations
- **Data Models**: Pydantic schemas for request/response validation
- **Background Tasks**: Scheduled jobs for data ingestion and alerts
- **Utility Functions**: AQI calculations, security, and data processing utilities
- **OpenAQ Integration**: Data ingestion from external API
- **Test Suite**: Comprehensive testing for all components

## Quick Start

### 1. Environment Setup

1. **Clone Repository**
   ```bash
   git clone <repository-url>
   cd air-quality-monitoring
   ```

2. **Create Virtual Environment**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # or
   source venv/bin/activate  # Linux/Mac
   ```

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### 2. Database Configuration

1. **Setup MongoDB Atlas** (Recommended)
   - Create account at [MongoDB Atlas](https://www.mongodb.com/atlas)
   - Create a new cluster
   - Create database user with read/write permissions
   - Get connection string

2. **Configure Environment Variables**
   ```bash
   cp .env.sample .env
   ```
   
   Edit `.env` file with your MongoDB credentials:
   ```properties
   MONGO_URI=mongodb+srv://your_username:your_password@your-cluster.mongodb.net/?retryWrites=true&w=majority
   MONGO_DB=air_quality_db
   ```

3. **Test Database Connection**
   ```bash
   python scripts/test_connection.py
   ```

4. **Create Database Indexes**
   ```bash
   python scripts/create_indexes.py
   ```

### 3. Run Application

1. **Development Server**
   ```bash
   cd backend
   python -m flask --app app.wsgi:app run --debug
   ```

2. **Access Application**
   - Dashboard: http://localhost:5000
   - API Base: http://localhost:5000/api

### 4. Verify Setup

After completing the above steps, you should see:
- MongoDB connection successful
- Database collections created: `stations`, `air_quality_data`
- Flask application running on port 5000

## Database Scripts and Utilities

The project includes several database utility scripts for setup and maintenance:

### Available Scripts

1. **test_connection.py** - MongoDB Connection Test
   ```bash
   python scripts/test_connection.py
   ```
   - Tests MongoDB connection using .env configuration
   - Displays database status and existing collections
   - Returns exit code 0 for success, 1 for failure (CI/CD friendly)

2. **create_indexes.py** - Database Index Creation
   ```bash
   python scripts/create_indexes.py
   ```
   - Creates optimized indexes for stations and air_quality_data collections
   - Idempotent: safe to run multiple times
   - Indexes created:
     - `stations.code` (unique)
     - `stations.loc` (2dsphere for geospatial queries)
     - `air_quality_data.station_id + ts_utc` (compound)
     - `air_quality_data.lat + lon + ts_utc` (compound)

### Script Output Examples

**Successful Connection Test:**
```
MongoDB Connection Test
----------------------------------------
Database: air_quality_db
URI: mongodb+srv://***@cluster.mongodb.net/...

Testing connection...
SUCCESS: MongoDB connection established
Collections found: 2
Collection names: air_quality_data, stations
----------------------------------------
Status: READY
```

**Index Creation:**
```
[indexes] stations
[indexes] air_quality_data
[done] indexes ensured.
```

## Technology Stack

- **Backend Framework**: Python 3.8+, Flask 2.3+
- **Database**: MongoDB Atlas (cloud) / MongoDB (local)
- **Frontend**: Jinja2 templates, Bootstrap 5, Chart.js, Leaflet maps
- **Task Scheduling**: APScheduler (planned)
- **Data Validation**: Pydantic v2 (planned)
- **Testing**: pytest (planned)
- **Environment Management**: python-dotenv
- **CI/CD**: GitHub Actions
- **External APIs**: OpenAQ API (planned)

## Configuration

### Environment Variables

Configure these variables in your `.env` file:

```properties
# MongoDB Configuration
MONGO_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
MONGO_DB=air_quality_db

# Flask Configuration  
SECRET_KEY=your-secret-key-here
FLASK_ENV=development
FLASK_DEBUG=True

# API Rate Limiting
API_RATE_LIMIT=60/minute

# Email Configuration (for alerts)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# OpenAQ API Configuration
OPENAQ_API_URL=https://api.openaq.org/v2
OPENAQ_API_KEY=your-openaq-api-key

# Feature Flags
ENABLE_PDF_EXPORT=false
```

## Development Workflow

### Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] MongoDB Atlas account created (or local MongoDB running)
- [ ] Environment variables configured in `.env`
- [ ] Dependencies installed via `pip install -r requirements.txt`
- [ ] Database connection tested successfully
- [ ] Database indexes created

### Next Steps for Development

1. **Implement Core Services**: Start with authentication and station management
2. **Database Integration**: Complete repository layer implementation
3. **API Implementation**: Build REST endpoint functionality
4. **OpenAQ Integration**: Develop data ingestion pipeline
5. **Frontend Development**: Enhance dashboard with interactive features
6. **Testing**: Add comprehensive test coverage
7. **Background Jobs**: Implement scheduled tasks for data processing

## Project Goals

This system aims to provide:
- **Real-time Monitoring**: Continuous air quality data collection and display
- **Data Analytics**: Historical trends, comparisons, and insights
- **Alert System**: Automated notifications for air quality thresholds
- **Public Access**: Easy-to-use dashboard for citizens and researchers
- **API Access**: REST endpoints for third-party integrations
- **Scalability**: Designed to handle multiple cities and data sources

## Documentation

- **API Reference**: See `docs/api.md` for detailed endpoint documentation
- **Database Design**: See `docs/db_schema.md` for data structure planning
- **Architecture**: See `docs/architecture.md` for system overview

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement functionality with tests
4. Ensure database scripts run successfully
5. Submit a pull request

This project follows clean architecture principles with clear separation between routes, business logic, and data access layers.
