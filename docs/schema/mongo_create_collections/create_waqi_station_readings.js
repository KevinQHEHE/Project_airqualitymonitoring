// waqi_station_readings (time-series)
db.createCollection("waqi_station_readings", {
  "timeseries": {
    "timeField": "ts",
    "metaField": "meta",
    "granularity": "hours"
  },
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "ts",
        "meta",
        "aqi",
        "time"
      ],
      "properties": {
        "ts": {
          "bsonType": "date"
        },
        "meta": {
          "bsonType": "object",
          "required": [
            "station_idx"
          ],
          "properties": {
            "station_idx": {
              "bsonType": "int"
            }
          },
          "additionalProperties": false
        },
        "aqi": {
          "oneOf": [
            {
              "bsonType": "double"
            },
            {
              "bsonType": "int"
            },
            {
              "bsonType": "long"
            },
            {
              "bsonType": "decimal"
            }
          ]
        },
        "time": {
          "bsonType": "object",
          "required": [
            "s",
            "tz"
          ],
          "properties": {
            "v": {
              "bsonType": "long"
            },
            "s": {
              "bsonType": "string"
            },
            "tz": {
              "bsonType": "string"
            }
          },
          "additionalProperties": false
        },
        "iaqi": {
          "bsonType": "object"
        }
      },
      "additionalProperties": false
    }
  }
});

// Helpful indexes
db.waqi_station_readings.createIndex({ "meta.station_idx": 1, ts: -1 });
db.waqi_station_readings.createIndex({ aqi: -1, ts: -1 });
// Optional TTL (365 days): uncomment below
// db.waqi_station_readings.createIndex({ ts: 1 }, { expireAfterSeconds: 31536000 });
