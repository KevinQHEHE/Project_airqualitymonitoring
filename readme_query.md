## MongoDB queries used by ingest/ and backup_dtb/

This file collects copy-paste-ready MongoDB queries and CLI commands that reflect the CRUD and admin operations used across the `ingest/` and `backup_dtb/` scripts in this repository.

Run these in `mongosh` (JS-style commands) or use the CLI tools (`mongoexport`, `mongoimport`) shown in PowerShell examples. Replace placeholder values (e.g. `12345`, `MONGO_DB`, file paths) with actual values before running.

---

### 1. Notes / variables

- Database name placeholder: `MONGO_DB` (e.g. `air_quality_db`)
- Example station index used for tests: `999999` (chosen to avoid collisions)
- Use `ISODate(...)` / `new Date()` in `mongosh` for dates. In PowerShell CLI examples we show environment variable use.

---

## Stations (upsert / query / update latest_reading_at)

Replace whole station document (replaceOne upsert):

```js
db.waqi_stations.replaceOne(
  { _id: 12345 },
  {
    _id: 12345,
    city: { name: "Hanoi" },
    geo: [21.0285, 105.8542],
    tz: "+07:00",
    created_at: new Date()
  },
  { upsert: true }
)
```

Update with $set / $setOnInsert:

```js
db.waqi_stations.updateOne(
  { _id: 12345 },
  {
    $set: { city: { name: "Hanoi" }, geo: [21.0285, 105.8542], tz: "+07:00" },
    $setOnInsert: { created_at: new Date() }
  },
  { upsert: true }
)
```

Flexible lookup (mimics `find_by_station_ids` that tries station_id, numeric forms, and ObjectId):

```js
db.waqi_stations.find({
  $or: [
    { station_id: { $in: ["12345", 12345] } },
    { _id: { $in: [ObjectId("PUT_OBJECTID_IF_ANY"), 12345] } }
  ]
}).pretty()
```

Update `latest_reading_at` (used by the ingestion to avoid duplicates):

```js
db.waqi_stations.updateOne(
  { _id: 12345 },
  { $set: { latest_reading_at: "2025-10-08T12:00:00+07:00" } },
  { upsert: false }
)
```

Count / find_one examples:

```js
db.waqi_stations.countDocuments({})
db.waqi_stations.findOne({ _id: 12345 })
```

---

## Checkpoints (insert + latest)

Insert a checkpoint document (used to detect whether to skip ingestion):

```js
db.current_reading_checkpoints.insertOne({
  timestamp: ISODate("2025-10-08T05:00:00Z"),
  created_at: new Date(),
  stats: { fetched: 100, note: "manual test" }
})
```

Get the most recent checkpoint (equivalent to find_one sorted by timestamp desc):

```js
db.current_reading_checkpoints.find().sort({ timestamp: -1 }).limit(1).pretty()
```

---

## Readings (bulk upsert and insert-only fallback)

Bulk upsert (bulkWrite of UpdateOne with upsert = true):

```js
const ops = [
  {
    updateOne: {
      filter: { 'meta.station_idx': 12345, ts: ISODate('2025-10-08T05:00:00Z') },
      update: { $set: {
        ts: ISODate('2025-10-08T05:00:00Z'),
        meta: { station_idx: 12345 },
        aqi: 42,
        time: { s: '2025-10-08 05:00:00', tz: '+07:00' },
        iaqi: { pm25: { v: 12 } }
      } },
      upsert: true
    }
  },
  // ... additional updateOne ops
];

db.waqi_station_readings.bulkWrite(ops, { ordered: false })
```

If server rejects update/upsert for time-series collections (fallback path), the script queries existing timestamps and inserts only missing docs:

Query existing timestamps:

```js
const tsList = [ ISODate('2025-10-08T05:00:00Z'), ISODate('2025-10-08T06:00:00Z') ];
db.waqi_station_readings.find({ 'meta.station_idx': 12345, ts: { $in: tsList } }, { ts: 1 }).toArray()
```

Insert missing readings (insertMany ordered=false):

```js
// missingDocs is an array of reading documents with ts normalized to Date and meta.station_idx set
db.waqi_station_readings.insertMany(missingDocs, { ordered: false })
```

Find latest readings for station (mimics `find_latest_by_station`):

```js
db.waqi_station_readings.find({ 'meta.station_idx': 12345 }).sort({ ts: -1 }).limit(10).pretty()
```

Query by time range:

```js
db.waqi_station_readings.find({
  station_id: '12345',
  ts: { $gte: ISODate('2025-10-01T00:00:00Z'), $lte: ISODate('2025-10-07T23:59:59Z') }
}).sort({ ts: 1 }).pretty()
```

Query by AQI range:

```js
db.waqi_station_readings.find({ aqi: { $gte: 50, $lte: 150 } }).pretty()
```

---

## Forecasts (conditional upserts used by forecast_ingest)

Upsert a forecast document (UpdateOne upsert):

```js
db.waqi_daily_forecasts.updateOne(
  { station_idx: 12345, day: '2025-10-09' },
  { $set: {
      station_idx: 12345,
      day: '2025-10-09',
      pollutants: { pm25: { avg: 12, min: 5, max: 20 } },
      fetched_at: new Date(),
      last_forecast_run_at: new Date()
    }
  },
  { upsert: true }
)
```

Retrieve existing forecasts for days (used to decide conditional update):

```js
db.waqi_daily_forecasts.find({ station_idx: 12345, day: { $in: ['2025-10-09', '2025-10-10'] } }).toArray()
```

Decision logic (performed by application code):
- Update if `run_at` > `last_forecast_run_at`, or pollutant values differ.

---

## Indexes (create indexes used by ensure_indexes)

```js
// Readings
db.waqi_station_readings.createIndex({ station_id: 1, ts: -1 })
db.waqi_station_readings.createIndex({ ts: -1 })
db.waqi_station_readings.createIndex({ location: '2dsphere' })

// Stations
db.waqi_stations.createIndex({ station_id: 1 }, { unique: true, partialFilterExpression: { station_id: { $exists: true, $ne: null } } })
db.waqi_stations.createIndex({ location: '2dsphere' })
db.waqi_stations.createIndex({ city: 1 })

// Forecasts
db.waqi_daily_forecasts.createIndex({ station_id: 1, forecast_date: -1 })
db.waqi_daily_forecasts.createIndex({ forecast_date: -1 })

// Users
db.users.createIndex({ email: 1 }, { unique: true })
db.users.createIndex({ username: 1 }, { unique: true })

// Password resets TTL
db.password_resets.createIndex({ tokenHash: 1 })
db.password_resets.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 })

// Cache TTL
db.email_validation_cache.createIndex({ email: 1 }, { unique: true })
db.email_validation_cache.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 })
db.api_response_cache.createIndex({ expiresAt: 1 }, { expireAfterSeconds: 0 })

// Alerts / logs
db.alert_subscriptions.createIndex({ user_id: 1 })
db.alert_subscriptions.createIndex({ station_id: 1 })
db.alert_subscriptions.createIndex({ station_id: 1, alert_threshold: 1, status: 1 })
db.notification_logs.createIndex({ subscription_id: 1 })
db.notification_logs.createIndex({ user_id: 1 })
db.notification_logs.createIndex({ station_id: 1 })
db.notification_logs.createIndex({ sentAt: 1 })
db.notification_logs.createIndex({ sentAt: 1 }, { expireAfterSeconds: 90 * 24 * 60 * 60 })
```

Note: If your MongoDB version does not support `partialFilterExpression`, create the unique index without it as fallback.

---

## Backup / Restore (export/import, timeseries, validators)

List collections and counts (helper used by backup script):

```js
db.getCollectionNames().forEach(function(c){
  print(c + ': ' + db.getCollection(c).countDocuments({}));
});
```

Export a collection to JSON Lines using `mongoexport` (PowerShell example):

```powershell
$Env:MONGO_URI = "mongodb://localhost:27017"
$Env:MONGO_DB = "air_quality_db"
mongoexport --uri="$Env:MONGO_URI" --db="$Env:MONGO_DB" --collection=waqi_stations --out=waqi_stations.jsonl
```

Import JSON Lines using `mongoimport`:

```powershell
mongoimport --uri="$Env:MONGO_URI" --db="$Env:MONGO_DB" --collection=waqi_stations --file=waqi_stations.jsonl --numInsertionWorkers=4
```

Create a time-series collection (restore uses metadata to do this):

```js
db.createCollection("waqi_station_readings", {
  timeseries: { timeField: "ts", metaField: "meta", granularity: "hours" }
})
```

Disable a collection validator before import (rollback script uses collMod):

```js
db.runCommand({ collMod: "collectionName", validator: {}, validationLevel: "off" })
```

Restore validator after import:

```js
db.runCommand({
  collMod: "collectionName",
  validator: { /* paste validator document from metadata */ },
  validationLevel: "strict",
  validationAction: "error"
})
```

Drop collection (replace-existing flow):

```js
db.getCollection('collectionName').drop()
```

Use `mongoimport` for streaming large JSONL files rather than reading them into mongosh.

---

## Repository-style examples (find_one, find_many, update_one, delete_one, count_documents)

Pagination (mimic `find_with_pagination`):

```js
const page = 1, page_size = 20, skip = (page - 1) * page_size;
const filter = {};
const total = db.waqi_stations.countDocuments(filter);
const stations = db.waqi_stations.find(filter).sort({ _id: 1 }).skip(skip).limit(page_size).toArray();
print('total:', total);
stations.forEach(s => printjson(s));
```

Update user by id:

```js
db.users.updateOne({ _id: ObjectId('PUT_OBJECT_ID') }, { $set: { role: 'admin', updatedAt: new Date() } })
```

Bulk update status (mimic `bulk_update_status`):

```js
db.users.updateMany({ _id: { $in: [ ObjectId('id1'), ObjectId('id2') ] } }, { $set: { isActive: false } })
```

Delete one station:

```js
db.waqi_stations.deleteOne({ _id: 12345 })
```

---

## Cleanup (remove test documents created by tests)

```js
db.waqi_stations.deleteOne({ _id: 999999 })
db.current_reading_checkpoints.deleteMany({ 'stats.marker': 'test_db_queries' })
db.waqi_station_readings.deleteMany({ 'meta.station_idx': 999999 })
db.waqi_daily_forecasts.deleteMany({ station_idx: 999999 })
db.test_restore_collection.deleteMany({ marker: 'test_db_queries' })
```

---

## Final notes

- These commands mirror the operations in the repository's `ingest/` and `backup_dtb/` scripts (replaceOne upserts for stations, bulkWrite updateOne upserts for readings/forecasts, insertMany fallback, index creation, collection ACL/validator adjustments during restore).
- Run them on a local/test database first. Backup production before destructive operations.
- If you'd like, I can:
  - add a `mongosh` smoke-test script (dry-run/execute toggle), or
  - run a subset of these commands on your local DB (I can execute them if you want me to run terminal commands).

If you'd like a runnable `mongosh` smoke-test script, tell me and I'll add it.
