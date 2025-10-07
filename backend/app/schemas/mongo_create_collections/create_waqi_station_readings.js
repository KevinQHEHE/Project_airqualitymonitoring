// Create timeseries collection: waqi_station_readings
// This collection stores air quality readings from stations over time

db.createCollection("waqi_station_readings", {
  timeseries: {
    timeField: "ts",
    metaField: "meta",
    granularity: "hours"
  }
});

// Create indexes for waqi_station_readings
// Note: Timeseries collections automatically create compound index on (meta, ts)
db.waqi_station_readings.createIndex({"meta.station_idx": 1, "ts": -1});
db.waqi_station_readings.createIndex({"ts": -1});
db.waqi_station_readings.createIndex({"location": "2dsphere"});
