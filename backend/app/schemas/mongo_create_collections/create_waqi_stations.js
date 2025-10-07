// Create collection: waqi_stations

db.createCollection("waqi_stations", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "_id",
        "station_id",
        "city"
      ],
      "properties": {
        "_id": {
          "bsonType": "int"
        },
        "station_id": {
          "bsonType": "int"
        },
        "city": {
          "bsonType": "object",
          "required": [
            "name",
            "url",
            "geo"
          ],
          "properties": {
            "name": {
              "bsonType": "string"
            },
            "url": {
              "bsonType": "string"
            },
            "geo": {
              "bsonType": "object",
              "required": [
                "type",
                "coordinates"
              ],
              "properties": {
                "type": {
                  "enum": [
                    "Point"
                  ]
                },
                "coordinates": {
                  "bsonType": "array",
                  "minItems": 2,
                  "maxItems": 2
                }
              }
            }
          }
        },
        "time": {
          "bsonType": "object",
          "properties": {
            "tz": {
              "bsonType": "string"
            }
          }
        },
        "attributions": {
          "bsonType": "array",
          "items": {
            "bsonType": "object",
            "properties": {
              "name": {
                "bsonType": "string"
              },
              "url": {
                "bsonType": "string"
              },
              "logo": {
                "bsonType": "string"
              }
            }
          }
        },
        "latest_reading_at": {
          "bsonType": "string"
        }
      }
    }
  }
});

// Create indexes for waqi_stations
db.waqi_stations.createIndex({"location": "2dsphere"});
db.waqi_stations.createIndex({"city": 1});
db.waqi_stations.createIndex({"station_id": 1}, { "unique": true });
