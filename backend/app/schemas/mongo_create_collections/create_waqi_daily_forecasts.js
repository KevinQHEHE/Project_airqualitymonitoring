// Create collection: waqi_daily_forecasts

db.createCollection("waqi_daily_forecasts", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "station_idx",
        "day",
        "fetched_at",
        "pollutants"
      ],
      "properties": {
        "station_idx": {
          "bsonType": "int"
        },
        "day": {
          "bsonType": "string"
        },
        "fetched_at": {
          "bsonType": "date"
        },
        "last_forecast_run_at": {
          "bsonType": "date"
        },
        "pollutants": {
          "bsonType": "object",
          "properties": {
            "pm25": {
              "bsonType": "object",
              "properties": {
                "avg": {
                  "bsonType": "int"
                },
                "min": {
                  "bsonType": "int"
                },
                "max": {
                  "bsonType": "int"
                }
              }
            },
            "pm10": {
              "bsonType": "object",
              "properties": {
                "avg": {
                  "bsonType": "int"
                },
                "min": {
                  "bsonType": "int"
                },
                "max": {
                  "bsonType": "int"
                }
              }
            }
          }
        }
      }
    }
  }
});

// Create indexes for waqi_daily_forecasts
db.waqi_daily_forecasts.createIndex({"station_id": 1, "forecast_date": -1});
db.waqi_daily_forecasts.createIndex({"forecast_date": -1});
