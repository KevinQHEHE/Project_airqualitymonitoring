// waqi_stations
db.createCollection("waqi_stations", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "_id",
        "city"
      ],
      "properties": {
        "_id": {
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
                  "maxItems": 2,
                  "items": {
                    "bsonType": "double"
                  }
                }
              }
            }
          },
          "additionalProperties": false
        },
        "time": {
          "bsonType": "object",
          "properties": {
            "tz": {
              "bsonType": "string"
            }
          },
          "additionalProperties": false
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
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    }
  }
});

db.waqi_stations.createIndex({ "city.geo": "2dsphere" });
db.waqi_stations.createIndex({ "city.name": 1 });
db.waqi_stations.createIndex({ "city.url": 1 });
