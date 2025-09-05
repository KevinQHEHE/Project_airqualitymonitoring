# API Documentation

## Authentication Endpoints
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout

## Station Management
- `GET /api/stations` - List all monitoring stations
- `POST /api/stations` - Create new station
- `GET /api/stations/{id}` - Get station details
- `PUT /api/stations/{id}` - Update station
- `DELETE /api/stations/{id}` - Delete station

## Measurements
- `GET /api/measurements` - Query air quality measurements
- `POST /api/measurements/import` - Import CSV data
- `GET /api/measurements/latest` - Get latest readings

## Aggregates & Analytics
- `GET /api/aggregates/daily` - Daily averages
- `GET /api/aggregates/monthly` - Monthly aggregates
- `GET /api/aggregates/ranking` - City rankings by AQI
- `GET /api/aggregates/trends` - Pollution trends

## Alerts Management
- `GET /api/alerts` - List user alerts
- `POST /api/alerts` - Create new alert
- `PUT /api/alerts/{id}` - Update alert settings
- `DELETE /api/alerts/{id}` - Delete alert

## Forecasts
- `GET /api/forecasts/{station_id}` - Get pollution forecasts
- `POST /api/forecasts/generate` - Generate new forecasts

## Exports
- `GET /api/exports/csv` - Export data as CSV
- `GET /api/exports/pdf` - Generate PDF reports

## Real-time Updates
- `GET /api/realtime/stream` - SSE endpoint for live updates
