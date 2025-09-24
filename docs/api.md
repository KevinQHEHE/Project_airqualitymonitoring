# API Documentation

## Authentication Endpoints
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - Revoke current access token
- `POST /api/auth/logout_refresh` - Revoke current refresh token

### Auth: Register & Login

Tokens
- Access token: JWT, expires in 1 hour
- Refresh token: JWT, expires in 7 days
- For protected endpoints, send `Authorization: Bearer <access_token>`

POST `/api/auth/register`
- Body (JSON):
```
{
  "username": "alice",
  "email": "alice@example.com",
  "password": "P@ssword123"
}
```
- Validation:
  - `username` required
  - `email` required and valid format
  - `password` policy: at least 8 chars, includes uppercase, lowercase, digit, and special character
- Errors: `400` invalid input; `409` duplicate email/username
- Response `201` (example):
```
{
  "message": "Registration successful",
  "user": {
    "id": "66fb9c...",
    "username": "alice",
    "email": "alice@example.com",
    "role": "user",
    "createdAt": "2025-09-15T10:00:00+00:00"
  },
  "access_token": "<jwt>",
  "refresh_token": "<jwt>"
}
```
- cURL:
```
curl -X POST "{{base_url}}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"P@ssword123"}'
```

POST `/api/auth/login`
- Body (JSON) using email or username:
```
{ "email": "alice@example.com", "password": "P@ssword123" }
```
or
```
{ "username": "alice", "password": "P@ssword123" }
```
- Errors: `400` missing fields; `401` invalid credentials
- Response `200`: same token/user shape as register
- cURL:
```
curl -X POST "{{base_url}}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"P@ssword123"}'
```

PowerShell (Windows)
```
# Register
$reg = @{ username = "alice"; email = "alice@example.com"; password = "P@ssword123" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/auth/register -ContentType "application/json" -Body $reg

# Login
$login = @{ email = "alice@example.com"; password = "P@ssword123" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/auth/login -ContentType "application/json" -Body $login

# Or send raw JSON directly
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/auth/login -ContentType "application/json" -Body '{"email":"alice@example.com","password":"P@ssword123"}'
```

Postman
- Import: `docs/postman/auth.postman_collection.json` (uses `{{base_url}}`)

Logout
- Revoke access token:
```
curl -X POST "{{base_url}}/api/auth/logout" \
  -H "Authorization: Bearer <access_token>"
```
- Revoke refresh token:
```
curl -X POST "{{base_url}}/api/auth/logout_refresh" \
  -H "Authorization: Bearer <refresh_token>"
```
- PowerShell (Windows):
```
$token = "<access_token>"
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/auth/logout -Headers @{ Authorization = "Bearer $token" }

$refresh = "<refresh_token>"
Invoke-RestMethod -Method Post -Uri http://localhost:5000/api/auth/logout_refresh -Headers @{ Authorization = "Bearer $refresh" }
```

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
- `GET /api/forecast/weekly?station_id={station_id}` - Returns aggregated daily statistics (min, max, avg) for `pm25`, `pm10`, and `uvi` computed from the air-quality readings collection (`waqi_station_readings`).

Notes:
- The API returns exactly N consecutive calendar days starting today (future window). Days with no data are padded with `null` values for the statistics.
- When raw readings are missing for a day but a precomputed forecast exists in the `waqi_daily_forecasts` collection, the endpoint will merge forecast values (pm25/pm10/uvi) from that collection as a non-blocking fallback. Readings-derived stats take precedence; merged values help fill gaps.

Query parameters:
- `station_id` (string|int, required) - station identifier
- `days` (integer, optional) - number of future days to return (default 9, min 1, max 14)

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
curl "http://localhost:5000/api/forecast/weekly?station_id=13668&days=9"
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

### Nearest Station Finder

GET `/api/stations/nearest` - Find monitoring stations nearest to a geographic point.

Query parameters (all sent as query params on a GET request):
- `lat` (required, number) - Latitude in decimal degrees. Range: `-90` to `90`.
- `lng` (required, number) - Longitude in decimal degrees. Range: `-180` to `180`.
- `radius` (optional, number) - Search radius in kilometers. Default: `25`. Maximum allowed: `25` (requests with a larger radius will be rejected).
- `limit` (optional, integer) - Maximum number of stations to return. Default: `5`. Maximum: `25`.

Validation rules:
- Missing or out-of-range `lat`/`lng` → `400 Bad Request` with JSON `{ "error": "<short message>" }`.
- Non-numeric `radius` or `limit` or values outside allowed bounds → `400 Bad Request`.

Behavior and notes:
- The endpoint uses the database's geospatial index (`2dsphere`) and MongoDB's `$geoNear` aggregation to return stations ordered by distance. The result includes the station basic info and the latest available reading (if any) from the `waqi_station_readings` collection.
- Returned distances are in kilometers and rounded to two decimal places (e.g. `1.23`).
- Responses are cached for 5 minutes in the server-side `api_response_cache` collection to reduce repeated work; cache entries use an `expiresAt` field and a TTL index created at application startup (see `backend/app/db.py` for index creation).
- If the geospatial index is missing, the server will fall back to a server-side Haversine-based filter (slower) and still return correct distances.
- Rate limiting: by default the route is limited to `100` requests per hour per user. If a valid JWT access token is provided the limiter keys by user identity; otherwise the limiter falls back to IP address. Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

Responses
- `200 OK` - Successful response with an array of stations ordered by proximity.
- `400 Bad Request` - Invalid or missing query parameters.
- `422 Unprocessable Entity` - No stations found within the requested radius.
- `429 Too Many Requests` - Rate limit exceeded.
- `500 Internal Server Error` - Unexpected server error.

Success response shape (example):
```
{
	"stations": [
		{
			"station_id": "13668",
			"name": "Station Name",
			"location": { "type": "Point", "coordinates": [106.8272, 10.8231] },
			"distance_km": 1.23,
			"latest_reading": {
				"aqi": 42,
				"pm25": 12.3,
				"pm10": 20.1,
				"o3": 0.01,
				"no2": 0.002,
				"so2": 0.0,
				"co": 0.1,
				"timestamp": "2025-09-24T12:00:00Z"
			}
		},
		...
	],
	"query": { "lat": 10.8231, "lng": 106.8272, "radius_km": 5, "limit": 3 }
}
```

Example cURL (default radius 25 km, default limit 5):
```
curl "http://localhost:5000/api/stations/nearest?lat=10.8231&lng=106.6297"
```

Example cURL (custom radius and limit):
```
curl "http://localhost:5000/api/stations/nearest?lat=10.8231&lng=106.6297&radius=5&limit=3"
```

PowerShell (Windows) example:
```
Invoke-RestMethod -Method Get -Uri "http://localhost:5000/api/stations/nearest?lat=10.8231&lng=106.6297&radius=5&limit=3"
```

Notes for integrators & operators:
- The caching TTL is 5 minutes to balance freshness and load — adjust the TTL and index settings in `backend/app/db.py` if you need a different policy.
- The endpoint expects the `waqi_station_readings` collection to include a timestamped reading per station; if no reading exists the `latest_reading` field will be `null`.
- For consistent rate-limiting behavior across a cluster, ensure your deployment provides a shared limiter storage (Redis) as configured in `backend/app/extensions.py` for `Flask-Limiter`.
- Tests: unit and integration tests for this endpoint live under `scripts_test/test_nearest_integration.py` (mocked DB). For full end-to-end testing consider running tests against a dedicated test MongoDB instance or `mongomock`.

Health & troubleshooting
- `GET /api/stations/health` - Lightweight health endpoint returning database connectivity and basic server info. Useful for monitoring and quick troubleshooting.

Example success response (HTTP `200`):
```
{
	"status": "healthy",
	"database": "air_quality_db",
	"server_version": "8.0.13",
	"collections": 10,
	"message": "Database connection is operational"
}
```

If the health endpoint reports `status: "unhealthy"` or the `nearest` endpoint returns `{"error":"Database unavailable"}` the server cannot reach MongoDB (check `MONGO_URI`, network access, credentials, and mongod process).

Cache clearing (debugging only): cached nearest responses are stored in the `api_response_cache` collection and expire automatically after 5 minutes. To clear cache immediately (development only):
```
mongosh "mongodb://localhost:27017/air_quality_db" --eval 'db.api_response_cache.deleteMany({})'
```

Trailing slash behavior:
- The `GET /api/stations` endpoint accepts both `/api/stations` and `/api/stations/` to avoid accidental redirects from clients or tooling (for example PowerShell/curl).

Why `nearest` might return no stations
- Confirm station documents have a GeoJSON `location` field with coordinates in `[longitude, latitude]` order. Example:
```
"location": { "type": "Point", "coordinates": [106.6297, 10.8231] }
```
- You can inspect a station via the API:
```
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/stations?limit=1" | ConvertTo-Json -Depth 10
```
or directly in MongoDB with `mongosh`:
```
mongosh "mongodb://localhost:27017/air_quality_db" --quiet --eval 'printjson(db.waqi_stations.findOne({}, {station_id:1, name:1, location:1, latitude:1, longitude:1, _id:0}))'
```

If station docs use `latitude`/`longitude` fields rather than a GeoJSON `location`, consider either backfilling a `location` field using those coordinates (recommended for indexing and performance) or using a non-indexed distance fallback (slower).

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

## Admin User Management

All endpoints require a valid admin access token (`Authorization: Bearer <jwt>`).

- `GET /api/admin/users` � List users with pagination (`page`, `page_size`), filters (`role`, `status`, `registered_after`, `registered_before`, `search`), and sorting (`sort`, `order`).
- `GET /api/admin/users/{id}` � Retrieve a single user including preferences and audit fields.
- `POST /api/admin/users` � Create a user with role assignment and optional preferences (`username`, `email`, `password`, `role`, `status`).
- `PUT /api/admin/users/{id}` � Update profile fields, role, status, password, or preferences.
- `DELETE /api/admin/users/{id}` � Soft delete (marks `status=inactive` and records `deletedAt`).
- `GET /api/admin/users/{id}/locations` � Return favorite stations and notification settings for the user.

Sample curl:
```
curl "http://localhost:5000/api/admin/users?page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```
