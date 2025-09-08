# perf/8-indexes-core — Core Indexes

## waqi_stations
- `city.geo` — 2dsphere
- `city.name` — B-Tree
- `city.url` — B-Tree 

## waqi_station_readings (time-series)
- `meta.station_idx, ts(desc)` — latest-per-station
- `aqi(desc), ts(desc)` 

## waqi_daily_forecasts
- `station_idx, day` (unique)
- `day`

## users
- `email` (unique), `username` (unique), `location` (2dsphere)

### Sample queries + explain
- GEO near (stations), city.name, latest reading, forecast range 

