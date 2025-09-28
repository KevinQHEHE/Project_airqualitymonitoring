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
│     ├─ wsgi.py                       # WSGI entrypoint for development and production deployment (moved to backend/)
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

### 🚧 To Be Implemented
The following components are structured but need implementation:
- **Business Logic**: Service layer implementations for each feature
- **Data Access**: Repository layer with MongoDB operations
- **Data Models**: Pydantic schemas for request/response validation
- **Background Tasks**: Scheduled jobs for data ingestion and alerts
- **Utility Functions**: AQI calculations, security, and data processing utilities
- **OpenAQ Integration**: Data ingestion from external API
- **Database Scripts**: Index creation and data seeding
- **Test Suite**: Comprehensive testing for all components

## Quick Start

1. **Clone and Setup Environment**
   ```bash
   git clone <repository-url>
   cd air-quality-monitoring
   cp .env.sample .env
   # Edit .env with your configuration
   ```

2. **Install Dependencies**
   ```bash
   pip install -e .[dev]
   ```

3. **Run Development Server**
   ```bash
   cd backend
   python -m flask --app wsgi:app run --debug
   ```

4. **Access Application**
   - Dashboard: http://localhost:5000
   - API Base: http://localhost:5000/api

## Technology Stack

- **Backend Framework**: Python 3.8+, Flask
- **Database**: MongoDB Atlas (planned)
- **Frontend**: Jinja2 templates, Chart.js, Leaflet maps (planned)
- **Task Scheduling**: APScheduler (planned)
- **Data Validation**: Pydantic (planned)
- **Testing**: pytest (planned)
- **CI/CD**: GitHub Actions
- **External APIs**: OpenAQ API (planned)

## Configuration

Key environment variables to configure in `.env`:
- `MONGO_URI`: MongoDB Atlas connection string
- `MONGO_DB`: Database name
- `MAIL_*`: Email server configuration for alerts
- `OPENAQ_API_URL`: OpenAQ API endpoint
- `SECRET_KEY`: Flask session encryption key

## Next Steps for Development

1. **Implement Core Services**: Start with authentication and station management
2. **Database Integration**: Connect MongoDB and implement repository layer
3. **API Implementation**: Complete REST endpoint implementations
4. **OpenAQ Integration**: Build data ingestion pipeline
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
4. Submit a pull request

This project follows clean architecture principles with clear separation between routes, business logic, and data access layers.
