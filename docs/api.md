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

Weekly statistics endpoint
- `GET /api/forecast/weekly?station_id={station_id}` - Returns aggregated daily statistics (min, max, avg) for `pm25`, `pm10`, and `uvi` computed from the `waqi_station_readings` collection.

Notes:
- The API returns only days that exist in the collection (no empty-day padding). If a station has readings for 1 day only within the 7-day window, the response will contain that single day.
- When raw readings are missing for a day but a precomputed forecast exists in the `waqi_daily_forecasts` collection, the endpoint will merge forecast values (pm25/pm10/uvi) from that collection as a fallback. Readings-derived stats take precedence; forecast-only days will be included when present.

Query parameters:
- `station_id` (string|int, required) - station identifier

Response shape (days present in DB):
```
{
	"station_id": "13668",
	"forecast": [
		{
			"date": "2025-09-08",
			"pm25_min": 5.2,
			"pm25_max": 23.1,
			"pm25_avg": 12.34,
			"pm10_min": 10.0,
			"pm10_max": 40.2,
			"pm10_avg": 22.11,
			"uvi_min": 0,
			"uvi_max": 6,
			"uvi_avg": 2.5
		},
		... (7 items)
	],
	"generated_at": "2025-09-14T12:00:00+00:00"
}
```

Example cURL:

```
curl "http://localhost:5000/api/forecast/weekly?station_id=13668"
```

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

History endpoint (new)

`GET /api/aq/history?station_id={station_id}&hours={hours}`

Query parameters:
- `station_id` (string|int, required) - station identifier
- `hours` (integer, optional) - lookback window in hours (default 12, max 72)

Response shape:
```
{
	"station_id": "13668",
	"measurements": [
		{"timestamp": "2025-09-13T10:00:00Z", "aqi": 42, "pm25": 12.3, "pm10": 20.1, "o3": 0.01, "no2": 0.002, "so2": 0.0, "co": 0.1, "pb": null},
		...
	]
}
```

Example cURL:

```
curl "http://localhost:5000/api/aq/history?station_id=13668&hours=12"
```

Example response:

```
{
	"measurements": [
		{
			"aqi": 25,
			"co": 1,
			"no2": 4,
			"o3": 1,
			"pm10": 25,
			"pm25": 18,
			"so2": 16,
			"station_id": 13668,
			"timestamp": "2025-09-13T02:00:00"
		},
		{
			"aqi": 52,
			"co": 1,
			"no2": 4,
			"o3": 16,
			"pm10": 47,
			"pm25": 52,
			"so2": 16,
			"station_id": 13668,
			"timestamp": "2025-09-13T12:00:00"
		},
		{
			"aqi": 52,
			"co": 1,
			"no2": 4,
			"o3": 11,
			"pm10": 44,
			"pm25": 52,
			"so2": 16,
			"station_id": 13668,
			"timestamp": "2025-09-13T13:00:00"
		},
		{
			"aqi": 48,
			"co": 1,
			"no2": 4,
			"o3": 9,
			"pm10": 39,
			"pm25": 48,
			"so2": 16,
			"station_id": 13668,
			"timestamp": "2025-09-13T14:00:00"
		}
	],
	"station_id": "13668"
}
```

If the browser does not pretty-print JSON, use the browser's "View Source" or a JSON formatter extension. Replace `localhost:5000` with your server host/port if different (for example `http://localhost:5001`).

Note: the application also registers an underscore-style route (`/api/air_quality/latest`) for backward compatibility, but examples here use the hyphenated path.

Acceptance mapping:
- GET `/api/stations` returns JSON list and pagination (AC: pass)
- Supports `limit` & `offset` (AC: pass)
- Postman/curl examples provided above (AC: pass)

