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

## Favorite Locations (User)

- Purpose: let users save favorite geographic locations, configure a nickname and an AQI alert threshold, and fetch current AQI for a saved favorite.
- Base path: `POST|GET|PUT|DELETE /api/user/favorites` and `GET /api/user/favorites/{id}/current`
- Authentication: JWT required. Send `Authorization: Bearer <access_token>`.

### Endpoints

- `POST /api/user/favorites` - Create or set a user's favorite location.
	- Accepts either a GeoJSON `location` object or legacy `latitude`/`longitude`.
	- Optional fields: `nickname` (string, max 100), `alert_threshold` (int 0-500, default 100).
	- Response: `201 Created` with favorite object (see shape below).

- `GET /api/user/favorites/` - List the user's favorites.
	- Note: Current implementation stores a single favorite per user (`users.location`) so this returns 0 or 1 item. When migrated to a dedicated collection this will return multiple entries.

- `GET /api/user/favorites/{id}` - Get a single favorite.
	- Current model ignores `{id}` and returns the user's stored location; kept for compatibility.

- `PUT /api/user/favorites/{id}` - Update favorite (nickname, alert_threshold, or location).
	- Accepts same payload shapes as `POST`.

- `DELETE /api/user/favorites/{id}` - Remove the favorite (unsets `users.location` in the current model).

- `GET /api/user/favorites/{id}/current` - Return current AQI for that location.
	- Current implementation returns `current_aqi: null` (placeholder). Recommended implementation: find nearest station via geospatial query on `waqi_stations` and fetch the latest reading from `waqi_station_readings`.

### Data shapes

- GeoJSON Point (location):
```
{
	"type": "Point",
	"coordinates": [<longitude>, <latitude>]
}
```

- Favorite (response):
```
{
	"id": "<optional id or omitted in single-location model>",
	"user_id": "<user ObjectId string>",
	"nickname": "Home",
	"alert_threshold": 100,
	"location": { "type": "Point", "coordinates": [lon, lat] },
	"createdAt": "2025-09-23T14:59:55.558+00:00",
	"updatedAt": "2025-09-23T14:59:55.558+00:00",
	"current_aqi": null  // or integer when available
}
```

### Validation rules

- `location` must be a GeoJSON `Point` with `coordinates` `[lon, lat]` where lon in [-180,180], lat in [-90,90]. Service will coerce coordinate values to floats (Mongo schema expects doubles).
- `alert_threshold` must be integer between 0 and 500. Default = 100.
- `nickname` must be a string up to 100 characters.
- Maximum favorites per user: planned `MAX_FAVORITES_PER_USER = 10` (not enforced in the current single-location model). When migrating to a dedicated `favorite_locations` collection this limit should be enforced in `create`.

### Examples

PowerShell (create):
```
$hdr = @{ Authorization = "Bearer $token" }
$body = @{ location = @{ type = "Point"; coordinates = @(21.0, 11.0) }; nickname = "Home"; alert_threshold = 120 } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:5000/api/user/favorites/' -Method Post -Headers $hdr -Body $body -ContentType 'application/json'
```

Curl (create):
```
curl -X POST http://localhost:5000/api/user/favorites/ \
	-H "Authorization: Bearer $token" \
	-H "Content-Type: application/json" \
	-d '{"location":{"type":"Point","coordinates":[21.0,11.0]},"nickname":"Home","alert_threshold":120}'
```

PowerShell (list):
```
Invoke-RestMethod -Uri 'http://localhost:5000/api/user/favorites/' -Method Get -Headers $hdr | ConvertTo-Json -Depth 10
```

PowerShell (current AQI):
```
Invoke-RestMethod -Uri 'http://localhost:5000/api/user/favorites/1/current' -Method Get -Headers $hdr | ConvertTo-Json -Depth 10
```

### Database notes & migration

- Current short-term storage: `users.location` (single favorite per user). The `create_users.js` schema requires `location` to be a GeoJSON Point with `coordinates` as doubles and the DB has a `2dsphere` index on `users.location`.
- Recommended long-term: create a dedicated `favorite_locations` collection with schema:
	- `_id, user_id(ObjectId), location(GeoJSON Point), nickname(string), alert_threshold(int), createdAt, updatedAt`
	- Indexes: `{ user_id: 1 }` and `{ location: '2dsphere' }`.
- Migration: add an idempotent script to copy `users.location` -> `favorite_locations` (or vice versa depending on chosen model). A helper `scripts/migrate_favorites_to_users.py` exists for one migration direction; adapt or add a new script for the other direction.

### Tests

- Unit tests for the service layer exist (`tests/test_favorites_service.py`). Add integration tests (Flask test client + JWT) to cover full request flow and to guard migration and multi-favorite behavior.

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
