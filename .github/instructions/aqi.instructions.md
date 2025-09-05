---
applyTo: '**'
---
# Copilot Agent Instructions – AQI Monitoring (Flask + MongoDB Atlas)

> **Purpose**  
> This document gives GitHub Copilot **strict, conflict-free** rules to generate code for the **exact** project scope:
> - **Flask REST API + Jinja UI** (Bootstrap + Chart.js + Leaflet)  
> - **MongoDB Atlas** as the only database  
> - **Data ingestion** (hourly/interval from OpenAQ)  
> - **Features**: Station & measurement CRUD/import, realtime dashboard (SSE or polling), basic aggregations, alerts (email), simple forecasts (moving average / linear regression), CSV/PDF export  
> - **Local-first** (then host later). Do **not** add unrequested components.

---

## 0) Repository Layout (fixed)

```
aqi-monitoring/
├─ README.md
├─ .gitignore
├─ .env.sample
├─ pyproject.toml
├─ config/
│  ├─ locations.yaml
│  └─ openaq.yaml
├─ docs/
│  ├─ COPILOT_AGENT.md      # (this file)
│  ├─ architecture.md
│  ├─ api.md
│  └─ db_schema.md
├─ backend/
│  └─ app/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ extensions.py
│     ├─ wsgi.py
│     ├─ blueprints/
│     │  ├─ auth/           # /api/auth/*
│     │  ├─ stations/       # /api/stations/*
│     │  ├─ measurements/   # /api/measurements/*
│     │  ├─ aggregates/     # /api/aggregates/*
│     │  ├─ alerts/         # /api/alerts/*
│     │  ├─ forecasts/      # /api/forecasts/*
│     │  ├─ exports/        # /api/exports/*
│     │  └─ dashboard/      # GET /  (Jinja UI + JS)
│     ├─ services/
│     ├─ repositories/
│     ├─ schemas/
│     ├─ tasks/             # APScheduler jobs
│     ├─ utils/
│     ├─ templates/
│     └─ static/
├─ ingest/
│  ├─ openaq_client.py
│  ├─ mapping.py
│  └─ run_ingest.py
├─ scripts/
│  ├─ create_indexes.py
│  ├─ seed_stations.py
│  ├─ ingest_once.sh
│  └─ run_dev.sh
└─ tests/
```

**Hard rule:** Copilot must **not** create files outside these folders or introduce new top-level apps/services.

---

## 1) Absolute Rules (applies to all generations)

1. **Scope lock:** Only generate code for the features listed in this file. **Do not** add auth providers, Celery, GraphQL, WebSockets, Docker, k8s, or extra frameworks.  
2. **Layers must not bleed:**
   - **Blueprints** (controllers): parse/validate, call service, return JSON or template.  
   - **Services**: domain logic; **no Flask request/response** here.  
   - **Repositories**: MongoDB (PyMongo) only; **no business rules**.  
3. **MongoDB Atlas only:** Read `MONGO_URI` & `MONGO_DB` from env. No local Mongo container.  
4. **Validation:** Use **Pydantic v2** in `schemas/`. Reject unknown fields if not explicitly allowed.  
5. **Errors:** Raise `AppError(status:int, message:str, detail:dict|None)` in services. Blueprints map to:
   ```json
   { "error": { "code": <int>, "message": "<string>", "detail": { ... } } }
   ```
6. **Security:**  
   - No secrets in code; no printing secrets.  
   - Rate-limit public GET endpoints with Flask-Limiter.  
   - Whitelist projections, sanitize filters; prevent user-controlled operators.  
   - Jinja escapes by default; avoid unsafe rendering.  
7. **Pagination:** Every list endpoint supports `page` (default 1) and `page_size` (default 20, max 100).  
8. **Typing & docs:** 100% type hints. Public functions/classes must have docstrings.  
9. **Small functions:** Keep functions cohesive (< ~60 lines).  
10. **Tests:** For new modules, provide **unit tests** (service/repo) and **integration tests** (blueprint). Use mongomock or a test DB. No external network in tests.  
11. **Imports:** Use absolute imports within `backend.app.*` to avoid circular imports.  
12. **UTC everywhere:** Time field is `ts_utc` (ISO 8601, UTC). Convert inputs to UTC.  
13. **No extraneous deps:** Only use libraries declared in `pyproject.toml`. If missing, do not add without a clear, small PR updating that file.

---

## 2) Data Model (collections & fields)

> Keep models lean and consistent. Use these field names and ranges.

- **users**
  - `email` (unique), `password_hash`, `role` in `{public,user,expert,admin}`, `created_at`
- **stations**
  - `code` (unique), `name`, `city`, `zip?`, `loc: { type:"Point", coordinates:[lng,lat] }`, `active`, `created_at`
- **air_quality_data` (aka `measurements`)**
  - `station_id` (ObjectId) **or** `lat, lon` if not station-mapped
  - `ts_utc` (ISO string), pollutants: `pm25, pm10, o3, no2, so2, co, pb?`
  - `aqi` (0..500), `source` (e.g., `"openaq"`), `created_at`
- **alerts**
  - `user_id`, `area` (Point|Polygon) or `zip`, `threshold` (AQI), `channels:["email"]`, `active`
- **forecasts**
  - `station_id`, `date` (UTC day/hour), `method:"ma"|"linreg"`, `horizon_h`, `aqi_pred`, `created_at`

**Indexes (create in `scripts/create_indexes.py`):**
- `users: {email:1} (unique)`
- `stations: {code:1} (unique), {loc:"2dsphere"}`
- `air_quality_data: {station_id:1, ts_utc:-1}, {lat:1, lon:1, ts_utc:-1}, {aqi:-1}`
- `forecasts: {station_id:1, date:-1}`

---

## 3) API Surface (keep stable)

- **Auth** `/api/auth/*`  
  - `POST /register`, `POST /login` (simple session/JWT—choose one, keep minimal)
- **Stations** `/api/stations/*`  
  - `GET` (filters: city, zip, near(lng,lat,radius_km), paginate), `POST`, `PUT /{id}`
- **Measurements** `/api/measurements/*`  
  - `GET` (by station_id or lat/lon, start/end, paginate)  
  - `POST /import` (multipart CSV)
- **Aggregates** `/api/aggregates/*`  
  - `GET /daily` (by city or station), `GET /ranking`, `GET /trend`
- **Alerts** `/api/alerts/*`  
  - `POST` register/update, `GET` list per user (auth required)
- **Forecasts** `/api/forecasts/*`  
  - `GET` by station_id, horizon(s)
- **Exports** `/api/exports/*`  
  - `GET /csv` (by range/filter).  
  - `GET /pdf` **if** `ENABLE_PDF_EXPORT=true`; otherwise return `501`.
- **Dashboard (Jinja)**  
  - `GET /` serves `templates/dashboard/index.html` with Bootstrap + Chart.js + Leaflet  
  - Use SSE `/api/realtime/stream` **or** 10–30s polling for realtime chart

**HTTP Codes:** 200/201/204, 400, 401, 403, 404, 409, 422, 429, 500.

---

## 4) File-Header Guards (paste to every new file)

### Blueprint
```python
# COPILOT-GUARD (Blueprint)
# - Controller only: parse/validate, call services.<module>_service, return JSON/template.
# - NO direct Mongo access. NO business logic here.
# - Validate JSON via @validate_json(PydanticModel); validate query with Pydantic TypeAdapter.
# - Map AppError → JSON error with correct HTTP status.
# - Public GET must use @limiter.limit("60/minute").
# - Enforce pagination: page=1, page_size=20 (max 100).
# - Absolute imports from backend.app.*, type hints + docstrings required.
```

### Service
```python
# COPILOT-GUARD (Service)
# - Pure business logic; NO Flask request/response here.
# - Use repositories.<module>_repo for DB operations.
# - Enforce domain invariants (uniqueness, ranges, roles).
# - Raise AppError(status:int, message:str, detail:dict|None) on errors.
# - Return plain dict/list (JSON-serializable), UTC times.
```

### Repository
```python
# COPILOT-GUARD (Repository)
# - Use flask_pymongo client from backend.app.extensions.mongo.
# - Whitelist filters; apply projection, sort, pagination.
# - Use defined indexes; do not add new without comment & script update.
# - NO business logic, NO role checks, return plain dict/list.
```

### Schema
```python
# COPILOT-GUARD (Schemas)
# - Pydantic v2 models (strict). Provide examples via model_config.json_schema_extra.
# - Validate AQI range 0..500; lat[-90..90], lon[-180..180]; iso datetimes (UTC).
# - Keep response models separate from write models if helpful.
```

### Tests
```python
# COPILOT-GUARD (Tests)
# - pytest. Cover happy + edge cases. No network calls (mock).
# - Routes: Flask test client fixture; assert status code & payload shape.
# - Repos: mongomock or test DB; seed minimal data.
# - Check pagination, rate limit, and validation errors.
```

---

## 5) Config & Constants

- Env (`.env`): `MONGO_URI`, `MONGO_DB`, `MAIL_*`, `API_RATE_LIMIT=60/minute`, `ENABLE_PDF_EXPORT=false`  
- **Time:** Always store & return `ts_utc` (UTC).  
- **AQI:** Return computed `aqi` in documents. Implement helper in `utils/aqi.py`.  
- **Roles:** `{public,user,expert,admin}`; protect mutating endpoints with role decorators.

---

## 6) Ingestion (OpenAQ)

- `ingest/openaq_client.py`: small HTTP client (requests), timeouts, retries/backoff.  
- `ingest/mapping.py`: map OpenAQ response → canonical `air_quality_data` document:
  ```
  { ts_utc, station_id? | (lat,lon), pm25, pm10, o3, no2, so2, co, pb?, aqi, source:"openaq" }
  ```
- `ingest/run_ingest.py`: CLI  
  - `--once` to ingest once for all configured locations in `config/*.yaml`  
  - `--interval <minutes>` to loop (hourly typical)

**Idempotency:** Upsert by key `(station_id, ts_utc)` or `(lat, lon, ts_utc)`.

---

## 7) Tasks (APScheduler)

- `tasks/ingest_openaq.py` – wraps the CLI ingestion inside the app if needed (dev mode).  
- `tasks/alerts_job.py` – every 5 min: find measurements with `aqi >= threshold` for each alert; send mail; write audit log.  
- `tasks/forecast_job.py` – hourly: moving average or linear regression per station; store in `forecasts`.

**Note:** Keep jobs small, idempotent, and safe on retries.

---

## 8) Frontend (Jinja + Bootstrap + Chart.js + Leaflet)

- `templates/dashboard/index.html`  
  - filters (city/zip/coords), line chart (Chart.js), markers (Leaflet)  
  - Color coding: **Green 0–50**, **Yellow 51–100**, **Red >100**  
- `static/js/dashboard.js`  
  - fetch `/api/aggregates/daily` + `/api/stations`  
  - realtime via `/api/realtime/stream` (SSE) or polling (10–30s)

Do **not** add SPA frameworks.

---

## 9) CSV/PDF Export

- CSV: always supported (`text/csv`), streamed if large.  
- PDF: only if `ENABLE_PDF_EXPORT=true`; otherwise return `501 Not Implemented`. If enabled, render HTML template and convert (lightweight lib only if already in deps). **Do not** add heavy deps silently.

---

## 10) Prompts for Copilot Chat (templates)

> **Generate module skeleton**
```
Create module "<name>":
1) schemas/<name>.py (Pydantic v2 request/response)
2) repositories/<name>_repo.py (PyMongo)
3) services/<name>_service.py (AppError on domain errors)
4) blueprints/<name>/routes.py (url_prefix="/api/<name>")
5) tests: test_<name>_service.py, test_<name>_routes.py
Apply all COPILOT-GUARD headers and project rules. Add pagination & validation.
```

> **Stations module**
```
Stations:
- GET /api/stations: filters city, zip, near(lng,lat,radius_km), pagination
- POST /api/stations: create (code unique, loc Point), roles: expert/admin
- PUT /api/stations/{id}: partial update (whitelist fields), roles: expert/admin
Add rate limit on GET. Use repositories.stations_repo via services.stations_service.
```

> **Measurements & CSV import**
```
Measurements:
- GET /api/measurements: by station_id or lat/lon + start/end UTC; pagination
- POST /api/measurements/import: multipart CSV; validate; compute AQI; batch insert with ordered=False; return counts
```

> **Aggregates**
```
Aggregates:
- /api/aggregates/daily (city or station, dateTrunc day, avg AQI asc)
- /api/aggregates/ranking (avg AQI by station within city, desc, limit)
- /api/aggregates/trend (time series by station)
Implement pipelines in repositories.measurements_repo.
```

> **Alerts**
```
Alerts:
- Model: user_id, area or zip, threshold, channels=["email"], active
- Service: scan_exceed_threshold() -> send email
- Blueprint: POST/GET; require auth for user-specific routes
```

> **Forecasts**
```
Forecasts:
- moving_average(station_id, window_hours=6) and linear_regression(horizon_h<=3)
- Persist to forecasts with {station_id, date, method, horizon_h, aqi_pred}
```

> **Dashboard + Realtime**
```
Dashboard:
- GET / renders Jinja template (Bootstrap layout)
- static/js/dashboard.js fetches aggregates and stations; SSE or polling
```

---

## 11) Definition of Done (every PR)

- ✅ Lint/format pass (`ruff`, `black`, `isort`)  
- ✅ Tests pass (`pytest`); unit + integration for new/changed code  
- ✅ Inputs validated (Pydantic); correct HTTP status & error schema  
- ✅ Pagination, projection, and role checks implemented as needed  
- ✅ No secrets in code/logs; no raw user operators to Mongo  
- ✅ `docs/api.md` updated with examples for any new endpoints

---

## 12) Red Flags (reject these)

- ❌ Direct DB calls in blueprints/templates  
- ❌ Mixing controller/service/repo in one file  
- ❌ Adding heavy/unknown deps without `pyproject.toml` update & justification  
- ❌ Skipping validation/tests or returning plain strings for errors  
- ❌ Non-UTC timestamps or inconsistent field names  
- ❌ Creating folders/files outside the fixed layout

---

## 13) Minimal Dependencies (reference)

- Flask ≥ 3.x, flask_pymongo, flask_login, flask_limiter, flask_mail, flask_caching  
- Pydantic ≥ 2.x, APScheduler, requests  
- pytest, mongomock, httpx  
- Bootstrap 5, Chart.js 4, Leaflet 1.9

> If a dependency is missing from `pyproject.toml`, **do not** import it. Propose a small PR that only adds the dependency + pins a compatible version.

---

## 14) Error Contract (exact JSON)
```json
{
  "error": {
    "code": 422,
    "message": "Validation error",
    "detail": [{ "loc": ["field"], "msg": "reason", "type": "pydantic_error" }]
  }
}
```

Use 4xx/5xx as appropriate; duplicate the HTTP code in `error.code`.

---

By following this document, Copilot must produce **consistent, testable, and minimal** code that exactly matches the project scope and structure—without conflicts or scope creep.
