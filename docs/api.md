# API Documentation
### Nearest Station Finder

GET `/api/stations/nearest` - Find monitoring stations nearest to a geographic point.

Query parameters
- `lat` (required, number) - Latitude in decimal degrees. Range: `-90` to `90`.
- `lng` (required, number) - Longitude in decimal degrees. Range: `-180` to `180`.
- `radius` (optional, number) - Search radius in kilometers. Default: `25`. Maximum allowed: `50` (requests with a larger radius will be rejected).
- `limit` (optional, integer) - Maximum number of stations to return. Default: `1`. Maximum: `25`.
- `units` (optional) - Not currently used; distances are returned in kilometers.

Validation & errors
- Missing or out-of-range `lat`/`lng` → `400 Bad Request` with JSON `{ "error": "<short message>" }`.
- Non-numeric `radius` or `limit` or values outside allowed bounds → `400 Bad Request`.

Behavior and implementation notes
- The endpoint prefers MongoDB's geospatial capability: it uses a `2dsphere` index and a `$geoNear` aggregation stage to return stations ordered by distance. If the `location` index is not present, the server falls back to an in-process Haversine scan over legacy coordinate fields (this is slower and only used as a fallback).
- The aggregation performs a `$lookup` into `waqi_station_readings` to attach the latest reading. The lookup matches readings by either `station_id` (string) or `meta.station_idx` (integer) and sorts by the normalized `ts` (UTC datetime) to select the newest reading.
- Distances are returned in kilometers and rounded to two decimal places (for example `1.23`).
- Responses are cached for 5 minutes in the `api_response_cache` collection to reduce repeated work. Cache entries use an `expiresAt` TTL index created at startup (see `backend/app/db.py`). When serving a cached entry the server will still attempt to enrich `latest_reading` by checking for a newer `ts` and refresh the cache when appropriate.
- Rate limiting: the route is limited (by default) to `100` requests per hour per user. When a valid JWT access token is supplied the limiter keys by user identity; otherwise it falls back to IP address. Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

Responses
- `200 OK` - Successful response with an array `stations` ordered by proximity. If no stations are found within the radius the response contains an empty `stations` array (older implementations sometimes returned `station: null`).
- `400 Bad Request` - Invalid or missing query parameters.
- `429 Too Many Requests` - Rate limit exceeded.
- `500 Internal Server Error` - Unexpected server error.

Success response shape (example)
```
{
	"stations": [
		{
			"station_id": "1583",
			"name": "Hanoi, Vietnam (Hà Nội)",
			"location": { "type": "Point", "coordinates": [105.8831, 21.0491] },
			"_distance_km": 0.00,
			"latest_reading": {
				"aqi": 9,
				"iaqi": { "pm25": { "v": 9 }, "pm10": { "v": 6 } },
				"time": { "iso": "2025-09-24T21:00:00+07:00", "s": "2025-09-24 21:00:00", "v": 1758747600 }
			}
		}
	],
	"query": { "lat": 21.0491, "lng": 105.8831, "radius_km": 25, "limit": 1 }
}
```

Examples

CURL
```
curl "{{base_url}}/api/stations/nearest?lat=21.0491&lng=105.8831&radius=25&limit=1"
```

PowerShell
```
Invoke-RestMethod -Method Get -Uri "http://localhost:5000/api/stations/nearest?lat=21.0491&lng=105.8831&radius=25&limit=1"
```

Notes for integrators & operators
- Ensure station documents include a GeoJSON `location` field with coordinates in `[longitude, latitude]` order. Example:
	```json
	"location": { "type": "Point", "coordinates": [106.6297, 10.8231] }
	```
- The lookup for `latest_reading` depends on ingest writing `ts` (UTC datetime) and, when available, `meta.station_idx` for integer-indexed matching. If your ingest omits these fields the returned `latest_reading` may be empty or stale.
- The public response is sanitized: internal debug fields are removed and `station_id` is the preferred client-facing identifier.
- For consistent rate-limiting in a clustered deployment, configure shared limiter storage (Redis) as described in `backend/app/extensions.py`.
- Tests for this endpoint live under `scripts_test/test_nearest_integration.py` (mocked DB). For end-to-end testing run against a dedicated test MongoDB instance or use `mongomock`.

Health & troubleshooting
- `GET /api/stations/health` - Lightweight health endpoint returning database connectivity and basic server info. Useful for monitoring and quick troubleshooting.

If the health endpoint reports `status: "unhealthy"` or the `nearest` endpoint returns `{"error":"Database unavailable"}` the server cannot reach MongoDB (check `MONGO_URI`, network access, credentials, and the mongod process).

Cache clearing (development only): cached nearest responses are stored in `api_response_cache` and expire after 5 minutes. To clear cache immediately (development use only):
```
mongosh "mongodb://localhost:27017/air_quality_db" --eval 'db.api_response_cache.deleteMany({})'
```

Why `nearest` might return no stations
- Confirm station documents have a GeoJSON `location` field and coordinates are stored as `[longitude, latitude]`.
- You can inspect a station via the API:
```
Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:5000/api/stations?limit=1" | ConvertTo-Json -Depth 10
```

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
The Alerts API exposes user notification preferences, subscription management, and an admin/test trigger for the monitoring job.

Base prefix: `/api/alerts`

Authentication & notes
- Many endpoints are admin/test or user-scoped. Where applicable the documentation notes whether a valid JWT is required. The `favorites` endpoint requires a JWT and enforces that the caller is the target user or an admin. The `notifications` update endpoint in the current implementation does not require a JWT (it merges the provided object into the user's preferences) — consider protecting this in production.

Endpoints

- `GET /api/alerts/health`
	- Returns: `{ "status": "ok" }` (200)

- `POST /api/alerts/trigger` (admin/test)
	- Purpose: trigger the favorite-stations monitor over HTTP (useful for QA/dev).
	- Protection: requires `ALERT_TEST_KEY` env var on the server. Client must send the same key either in header `X-ALERT-TEST-KEY` or as query param `?key=<key>`.
	- Responses:
		- `200` { "message": "monitor invoked" }
		- `403` forbidden when key is missing or wrong
		- `503` when server not configured with `ALERT_TEST_KEY`
		- `500` when monitor invocation failed

- `PUT /api/alerts/user/<user_id>/favorites` (requires JWT)
	- Purpose: set a user's `preferences.favoriteStations` list (array of station ids).
	- Auth: `Authorization: Bearer <access_token>` required. Only the owning user or admins may update.
	- Body JSON: `{ "favoriteStations": [123, 456] }` (array of numbers or strings)
	- Responses:
		- `200` { "message": "favorites updated", "favoriteStations": [...] }
		- `400` if payload missing or invalid
		- `401` authorization required (if no/invalid JWT)
		- `403` forbidden if caller not owner/admin
		- `404` user not found
		- `500` on DB error
	- Notes: Monitor discovers users to evaluate by checking `preferences.notifications.enabled == true` and that `preferences.favoriteStations` exists and is not empty.

- `GET /api/alerts/user/<user_id>/notifications`
	- Returns the `preferences.notifications` object for the user. `200` or `404` if user not found.

- `PUT /api/alerts/user/<user_id>/notifications`
	- Body: JSON object to set/replace the `preferences.notifications` object (e.g. `{ "enabled": true, "threshold": 80 }`).
	- Response: `200` { "message": "notifications updated", "notifications": <object> } or `400` on invalid body.
	- Note: current implementation does not require a JWT; consider protecting.

- Subscriptions CRUD (`/api/alerts/subscriptions`)
	- `GET /api/alerts/subscriptions?user_id=<oid>&station_id=<id>`
		- List subscriptions filtered by optional `user_id` (ObjectId string) and/or `station_id` (string).
		- Response: `200` { "subscriptions": [ ... ] }

	- `POST /api/alerts/subscriptions`
		- Body JSON: `{ "user_id": "<oid>", "station_id": "<id>", "alert_threshold": 100, "metadata": {...} }`
		- Creates a subscription document and returns `201` { "subscription_id": "<id>" }.
		- Errors: `400` missing/invalid fields, `500` internal error (DB failure). The endpoint currently inserts a new record; creating uniqueness constraints (user+station active) is recommended to avoid duplicates.

	- `GET /api/alerts/subscriptions/<sub_id>`
		- Returns subscription document or `404`.

	- `PUT /api/alerts/subscriptions/<sub_id>`
		- Body fields allowed to update: `alert_threshold`, `status`, `metadata`.
		- Returns `200` on success or `400`/`404`/`500` on error.

	- `DELETE /api/alerts/subscriptions/<sub_id>`
		- Soft-delete: sets `status` to `expired` and updates `updatedAt`. Returns `200` on success.

- `GET /api/alerts/logs` — list `notification_logs`
	- Query params: `user_id` (ObjectId), `station_id` (string), `status` (delivered|failed|bounced|deferred), `page`, `page_size`.
	- Response: `200` { "logs": [ ... ], "page": 1, "page_size": 50 }
	- Notes: Each log contains fields: `_id`, `subscription_id` (nullable), `user_id`, `station_id`, `sentAt`, `status` (delivered/failed/deferred), `attempts`, `response`, `message_id`.

Examples

CURL (update favorites):
```
curl -X PUT "{{base_url}}/api/alerts/user/<user_id>/favorites" \
	-H "Authorization: Bearer <access_token>" \
	-H "Content-Type: application/json" \
	-d '{"favoriteStations":[5506,8688]}'
```

CURL (create subscription):
```
curl -X POST "{{base_url}}/api/alerts/subscriptions" \
	-H "Content-Type: application/json" \
	-d '{"user_id":"<oid>","station_id":"8688","alert_threshold":200}'
```

CURL (list logs):
```
curl "{{base_url}}/api/alerts/logs?user_id=<oid>&station_id=8688"
```

Notes & recommendations
- Monitor discovery: the scheduled monitor reads users where `preferences.notifications.enabled` is true and `preferences.favoriteStations` is present and not empty. Creating a subscription alone will not cause the monitor to evaluate the user unless the station is listed in the user's favorites.
- Rate-limiting: monitor enforces 1 alert per user-station per 24 hours. Re-running tests may require removing recent `notification_logs` entries or using a test-only `force_send` flag.
- Idempotency: consider adding a unique index on `(user_id, station_id, status='active')` and returning existing subscription id when a duplicate is attempted.

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
- `radius` (optional, number) - Search radius in kilometers. Default: `25`. Maximum allowed: `50` (requests with a larger radius will be rejected).
- `limit` (optional, integer) - Maximum number of stations to return. Default: `1` (the endpoint commonly returns the single nearest station). Maximum: `25`.

Validation rules:
- Missing or out-of-range `lat`/`lng` → `400 Bad Request` with JSON `{ "error": "<short message>" }`.
- Non-numeric `radius` or `limit` or values outside allowed bounds → `400 Bad Request`.

Behavior and notes:
- The endpoint uses the database's geospatial index (`2dsphere`) and MongoDB's `$geoNear` aggregation to return stations ordered by distance. If a `location` index is not available, the server falls back to an in-process Haversine scan across legacy fields (slower).
- The aggregation stage performs a `$lookup` into `waqi_station_readings` to attach the latest reading. The lookup now matches readings by either `station_id` (string) or `meta.station_idx` (integer), and orders readings by the normalized `ts` field (UTC datetime) to ensure the most recent reading is returned.
- Returned distances are in kilometers and rounded to two decimal places (e.g. `1.23`).
- Responses are cached for 5 minutes in the server-side `api_response_cache` collection to reduce repeated work; cache entries use an `expiresAt` field and a TTL index created at application startup (see `backend/app/db.py` for index creation). When a cached nearest entry is returned the server will attempt to enrich the cached `latest_reading` by checking the readings collection for a newer `ts` and refresh the cache if necessary.
- Rate limiting: by default the route is limited to `100` requests per hour per user. If a valid JWT access token is provided the limiter keys by user identity; otherwise the limiter falls back to IP address. Exceeding the limit returns `429 Too Many Requests` with a `Retry-After` header.

Responses
- `200 OK` - Successful response with station(s) ordered by proximity.
- `400 Bad Request` - Invalid or missing query parameters.
- `404 Not Found` - No stations found within the requested radius (the endpoint returns a `200` with `station: null` in some fallback cases; check message in response).
- `429 Too Many Requests` - Rate limit exceeded.
- `500 Internal Server Error` - Unexpected server error.

Success response shape (example):
```
{
 	"stations": [
 		{
 			"station_id": "1583",
 			"name": "Hanoi, Vietnam (Hà Nội)",
 			"location": { "type": "Point", "coordinates": [105.8831, 21.0491] },
 			"_distance_km": 0.0,
 			"latest_reading": {
 				"aqi": 9,
 				"iaqi": { "pm25": {"v": 9}, "pm10": {"v": 6}, ... },
 				"time": { "iso": "2025-09-24T21:00:00+07:00", "s": "2025-09-24 21:00:00", "v": 1758747600 }
 			}
 		}
 	],
 	"query": { "lat": 21.0491, "lng": 105.8831, "radius_km": 25, "limit": 1 }
}
```

Notes for integrators & operators:
- The aggregation `$lookup` matches readings by `station_id` (string) or `meta.station_idx` (integer) and sorts on `ts` (UTC datetime) to find the most recent reading; ensure your ingest writes `ts` and (when applicable) `meta.station_idx` for reliable lookups.
- The public response is sanitized: debug/internal fields like `dist` and `city_geo` are removed, the nested `city.geo` object is dropped if a top-level `location` is present (to avoid duplicated coordinate blobs), and `station_id` is preferred as the client-facing identifier (the internal `_id` is removed when `station_id` exists).
- Cache: cached entries are pruned of debug/internal fields before persistence so cache contents are safe to serve. Cache entries are refreshed automatically when a newer `ts`-based reading is detected.
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
