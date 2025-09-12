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

Curl examples:

Get first 10 stations:
```
curl -s "http://localhost:5000/api/stations?limit=10&offset=0" | jq
```

Filter by city:
```
curl -s "http://localhost:5000/api/stations?city=Hanoi" | jq
```

Postman collection: `docs/postman/get-stations.postman_collection.json` (set `{{base_url}}` environment variable)

PowerShell (Windows) examples

PowerShell's `Invoke-RestMethod`/`Invoke-WebRequest` are preferred on Windows. Note the trailing slash to avoid a redirect from the server (the blueprint route uses `/`):

Pretty-print JSON with `Invoke-RestMethod`:
```powershell
Invoke-RestMethod -Uri "http://localhost:5000/api/stations/?limit=10&offset=0" |
	ConvertTo-Json -Depth 10
```

Alternatively (parse and reformat):
```powershell
(Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:5000/api/stations/?limit=10&offset=0").Content |
	ConvertFrom-Json |
	ConvertTo-Json -Depth 10
```

If you have Python available in the venv, you can pipe to Python's json.tool:
```powershell
curl "http://localhost:5000/api/stations/?limit=10&offset=0" | python -m json.tool
```

Acceptance mapping:
- GET `/api/stations` returns JSON list and pagination (AC: pass)
- Supports `limit` & `offset` (AC: pass)
- Postman/curl examples provided above (AC: pass)

