// waqi_station_readings (time-series)
db.createCollection("waqi_station_readings", {
  "timeseries": {
    "timeField": "ts",
    "metaField": "meta",
    "granularity": "hours"
  }
});

// Helpful indexes
db.waqi_station_readings.createIndex({ "meta.station_idx": 1, ts: -1 });
db.waqi_station_readings.createIndex({ aqi: -1, ts: -1 });
// db.waqi_station_readings.createIndex({ ts: 1 }, { expireAfterSeconds: 31536000 });
