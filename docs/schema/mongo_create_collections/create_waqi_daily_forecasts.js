// waqi_daily_forecasts
db.createCollection("waqi_daily_forecasts", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "station_idx",
        "day",
        "pollutants"
      ],
      "properties": {
        "station_idx": {
          "bsonType": "int"
        },
        "day": {
          "bsonType": "string"
        },
        "pollutants": {
          "bsonType": "object",
          "properties": {
            "pm25": {
              "bsonType": "object",
              "required": [
                "avg",
                "min",
                "max"
              ],
              "properties": {
                "avg": {
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
                "min": {
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
                "max": {
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
                }
              },
              "additionalProperties": false
            },
            "pm10": {
              "bsonType": "object",
              "required": [
                "avg",
                "min",
                "max"
              ],
              "properties": {
                "avg": {
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
                "min": {
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
                "max": {
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
                }
              },
              "additionalProperties": false
            },
            "o3": {
              "bsonType": "object",
              "required": [
                "avg",
                "min",
                "max"
              ],
              "properties": {
                "avg": {
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
                "min": {
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
                "max": {
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
                }
              },
              "additionalProperties": false
            },
            "uvi": {
              "bsonType": "object",
              "required": [
                "avg",
                "min",
                "max"
              ],
              "properties": {
                "avg": {
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
                "min": {
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
                "max": {
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
                }
              },
              "additionalProperties": false
            }
          },
          "additionalProperties": false
        },
        "fetched_at": {
          "bsonType": "date"
        }
      },
      "additionalProperties": false
    }
  }
});

db.waqi_daily_forecasts.createIndex({ station_idx: 1, day: 1 }, { unique: true });
db.waqi_daily_forecasts.createIndex({ day: 1 });
