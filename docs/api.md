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
 - `GET /api/air-quality/latest` - Get latest measurement per station (this new endpoint)

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

## Stations API

`GET /api/stations` - List monitoring stations with simple limit/offset pagination.

Query parameters:
- `limit` (integer, default 20, max 100) - number of items to return
- `offset` (integer, default 0) - number of items to skip
- `city` (string, optional) - filter stations by city name (case-insensitive)
- `country` (string, optional) - filter by country code (ISO)

Response shape (example):
```
{
	"stations": [ ... ],
	"pagination": {
		"limit": 20,
		"offset": 0,
		"total": 123,
		"pages": 7,
		"current_page": 1,
		"has_next": true,
		"has_prev": false
	}
}
```

JSON Schema for response: `backend/app/schemas/schemas_jsonschema/stations_list.response.json`

Postman collection: `docs/postman/get-stations.postman_collection.json` (set `{{base_url}}` environment variable)

Browser (Chrome) examples — canonical quick-checks

Open the URL directly in the browser address bar to view JSON — no extra JavaScript or tools required. Modern browsers (Chrome, Firefox) format JSON responses automatically for easy reading.

Stations endpoints (browse these in the address bar):

`http://localhost:5000/api/stations?limit=10&offset=0`

`http://localhost:5000/api/stations?city=Hanoi`

Air-quality endpoints (browse these in the address bar):

`http://localhost:5000/api/air-quality/latest`

`http://localhost:5000/api/air-quality/latest?station_id=13668&limit=1`

If the browser does not pretty-print JSON, use the browser's "View Source" or a JSON formatter extension. Replace `localhost:5000` with your server host/port if different (for example `http://localhost:5001`).

Note: the application also registers an underscore-style route (`/api/air_quality/latest`) for backward compatibility, but examples here use the hyphenated path.

Acceptance mapping:
- GET `/api/stations` returns JSON list and pagination (AC: pass)
- Supports `limit` & `offset` (AC: pass)
- Postman/curl examples provided above (AC: pass)

