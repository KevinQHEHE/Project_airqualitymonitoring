
## Flow 1: Import Thông tin Trạm

### Bulk Upsert Stations

```javascript
// Bulk upsert stations vào collection waqi_stations
db.waqi_stations.bulkWrite([
  {
    updateOne: {
      filter: { _id: <station_idx> },
      update: { $set: <station_document> },
      upsert: true
    }
  }
])

// Kiểm tra kết quả
db.waqi_stations.countDocuments()
db.waqi_stations.findOne()
db.waqi_stations.getIndexes()
```


## Flow 2: Thu thập Dữ liệu Hàng giờ

### Check Last Checkpoint

```javascript
db.current_reading_checkpoints.findOne(
  {},
  { sort: { timestamp: -1 } }
)
```


### Get All Station IDs

```javascript
db.waqi_stations.find(
  {},
  { _id: 1, "city.name": 1 }
)
```


### Check Duplicate Reading

```javascript
// Lấy latest_reading_at của station
db.waqi_stations.findOne(
  { _id: <station_idx> },
  { latest_reading_at: 1 }
)
```


### Insert Reading

```javascript
// Insert one reading
db.waqi_station_readings.insertOne({
  ts: <normalized_datetime_utc>,
  meta: { station_idx: <station_idx> },
  aqi: <aqi_value>,
  time: {
    s: "2025-09-11 12:00:00",
    tz: "+07:00",
    iso: "2025-09-11T12:00:00+07:00"
  },
  iaqi: { /* pollutant values */ }
})

// Bulk upsert
db.waqi_station_readings.bulkWrite([
  {
    updateOne: {
      filter: { 
        "meta.station_idx": <station_idx>,
        ts: <timestamp>
      },
      update: { $set: <reading_document> },
      upsert: true
    }
  }
])
```


### Update Latest Reading

```javascript
db.waqi_stations.updateOne(
  { _id: <station_idx> },
  { $set: { latest_reading_at: <time_iso> } },
  { upsert: false }
)
```


### Save Checkpoint

```javascript
db.current_reading_checkpoints.insertOne({
  timestamp: <normalized_hour_utc>,
  created_at: <current_datetime_utc>,
  stats: {
    total_stations: <count>,
    successful_stations: <count>,
    failed_stations: <count>,
    total_readings: <count>
  }
})
```


### Queries Kiểm tra

```javascript
// Xem readings của một station
db.waqi_station_readings.find(
  { "meta.station_idx": <station_idx> }
).sort({ ts: -1 }).limit(10)

// Đếm số readings
db.waqi_station_readings.countDocuments({
  "meta.station_idx": <station_idx>
})
```


## Flow 3: Thu thập Dự báo 7 ngày

### Get Existing Forecasts

```javascript
db.waqi_daily_forecasts.find({
  station_idx: <station_idx>,
  day: { $in: [<list_of_days_YYYY-MM-DD>] }
})
```


### Check Existing Forecast

```javascript
db.waqi_daily_forecasts.findOne({
  station_idx: <station_idx>,
  day: "2025-10-15"
})
```


### Bulk Upsert Forecasts

```javascript
db.waqi_daily_forecasts.bulkWrite([
  {
    updateOne: {
      filter: { 
        station_idx: <station_idx>,
        day: <day_YYYY-MM-DD>
      },
      update: {
        $set: {
          station_idx: <station_idx>,
          day: <day_YYYY-MM-DD>,
          pollutants: {
            pm25: { avg: <val>, min: <val>, max: <val> },
            pm10: { avg: <val>, min: <val>, max: <val> },
            o3: { avg: <val>, min: <val>, max: <val> },
            uvi: { avg: <val>, min: <val>, max: <val> }
          },
          fetched_at: <datetime_utc>,
          last_forecast_run_at: <run_at_datetime_utc>
        }
      },
      upsert: true
    }
  }
], { ordered: false })
```


### Queries Kiểm tra

```javascript
// Xem forecasts của station
db.waqi_daily_forecasts.find({
  station_idx: <station_idx>
}).sort({ day: 1 })

// Kiểm tra last run
db.waqi_daily_forecasts.aggregate([
  {
    $group: {
      _id: null,
      latest_run: { $max: "$last_forecast_run_at" },
      total_forecasts: { $sum: 1 }
    }
  }
])
```


## Flow 4a: Backup Database

### List Collections

```javascript
db.getCollectionNames()

// Với metadata
db.runCommand({ listCollections: 1 })
```


### Stream Documents

```javascript
db.<collection_name>.find({}).batchSize(1000)

// Examples
db.waqi_stations.find({}).batchSize(1000)
db.waqi_station_readings.find({}).batchSize(1000)
db.waqi_daily_forecasts.find({}).batchSize(1000)
```


### Get Collection Metadata

```javascript
db.runCommand({
  listCollections: 1,
  filter: { name: <collection_name> }
})
```


## Flow 4b: Restore Database

### Build Restore Plan

```javascript
db.getCollectionNames()
```


### Disable Validators

```javascript
db.runCommand({
  collMod: <collection_name>,
  validator: {},
  validationLevel: "off"
})
```


### Drop \& Recreate Collections

```javascript
db.<collection_name>.drop()

// Time-series collection
db.createCollection("<collection_name>", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "hours"
  }
})
```


### Batch Insert

```javascript
db.<collection_name>.insertMany(
  [<batch_of_1000_documents>],
  { ordered: false }
)
```


### Restore Validators

```javascript
db.runCommand({
  collMod: <collection_name>,
  validator: <validator_object>,
  validationLevel: "strict",
  validationAction: "error"
})
```


### Verify Restore

```javascript
// Document counts
db.getCollectionNames().forEach(function(collName) {
  print(collName + ": " + db[collName].countDocuments());
});

// Verify indexes
db.getCollectionNames().forEach(function(collName) {
  print("\n" + collName + " indexes:");
  printjson(db[collName].getIndexes());
});
```


## Compound Keys \& Indexes

### waqi_stations

```javascript
db.waqi_stations.createIndex({ "_id": 1 })
db.waqi_stations.createIndex({ "city.geo.coordinates": "2dsphere" })
```


### waqi_station_readings

```javascript
db.waqi_station_readings.createIndex({ "meta.station_idx": 1, "ts": -1 })
db.waqi_station_readings.createIndex({ "ts": -1 })
```


### waqi_daily_forecasts

```javascript
db.waqi_daily_forecasts.createIndex({ "station_idx": 1, "day": 1 }, { unique: true })
db.waqi_daily_forecasts.createIndex({ "day": 1 })
db.waqi_daily_forecasts.createIndex({ "last_forecast_run_at": -1 })
```


### current_reading_checkpoints

```javascript
db.current_reading_checkpoints.createIndex({ "timestamp": -1 })
```


## Debugging Queries

### Data Integrity

```javascript
// Find stations without readings
db.waqi_stations.aggregate([
  {
    $lookup: {
      from: "waqi_station_readings",
      localField: "_id",
      foreignField: "meta.station_idx",
      as: "readings"
    }
  },
  {
    $match: {
      readings: { $size: 0 }
    }
  },
  {
    $project: {
      _id: 1,
      "city.name": 1
    }
  }
])

// Find duplicate readings
db.waqi_station_readings.aggregate([
  {
    $group: {
      _id: {
        station_idx: "$meta.station_idx",
        ts: "$ts"
      },
      count: { $sum: 1 }
    }
  },
  {
    $match: {
      count: { $gt: 1 }
    }
  }
])
```


### Performance Monitoring

```javascript
// Collection stats
db.waqi_station_readings.stats()

// Index usage
db.waqi_station_readings.aggregate([
  { $indexStats: {} }
])

// Explain query plan
db.waqi_station_readings.find({
  "meta.station_idx": 123
}).sort({ ts: -1 }).limit(10).explain("executionStats")
```

