// Helper script to create alert_subscriptions and notification_logs collections
// Run with: mongo <uri>/<db> create_alert_collections.js

const subsValidator = cat('schemas/mongo_validators/alert_subscriptions.validator.json');
const logsValidator = cat('schemas/mongo_validators/notification_logs.validator.json');

// Create or update alert_subscriptions
try {
  db.createCollection('alert_subscriptions', { validator: subsValidator, validationLevel: 'moderate' });
  print('Created alert_subscriptions collection');
} catch (e) {
  print('alert_subscriptions exists or failed to create: ' + e);
}

// Create or update notification_logs
try {
  db.createCollection('notification_logs', { validator: logsValidator, validationLevel: 'moderate' });
  print('Created notification_logs collection');
} catch (e) {
  print('notification_logs exists or failed to create: ' + e);
}

// Ensure indexes for alert_subscriptions
try {
  db.alert_subscriptions.createIndex({ user_id: 1 });
  db.alert_subscriptions.createIndex({ station_id: 1 });
  // composite for querying subscriptions by station and threshold (e.g., find subscriptions where threshold <= current aqi)
  db.alert_subscriptions.createIndex({ station_id: 1, alert_threshold: 1, status: 1 });
  // ensure quick lookup by user and status
  db.alert_subscriptions.createIndex({ user_id: 1, status: 1 });
  print('Indexes created for alert_subscriptions');
} catch (e) {
  print('Failed creating indexes on alert_subscriptions: ' + e);
}

// Ensure indexes for notification_logs
try {
  db.notification_logs.createIndex({ subscription_id: 1 });
  db.notification_logs.createIndex({ user_id: 1 });
  db.notification_logs.createIndex({ station_id: 1 });
  db.notification_logs.createIndex({ sentAt: 1 });
  // TTL for retention policy: keep logs for 90 days
  const ninetyDaysSeconds = 90 * 24 * 60 * 60;
  try {
    db.notification_logs.createIndex({ sentAt: 1 }, { expireAfterSeconds: ninetyDaysSeconds });
  } catch (e) {
    print('Could not create TTL index on notification_logs.sentAt: ' + e);
  }
  print('Indexes created for notification_logs (including TTL)');
} catch (e) {
  print('Failed creating indexes on notification_logs: ' + e);
}


// Create collection: alert_subscriptions

db.createCollection("alert_subscriptions", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "user_id",
        "station_id",
        "alert_threshold",
        "status",
        "createdAt"
      ],
      "properties": {
        "user_id": {
          "bsonType": "objectId"
        },
        "station_id": {
          "bsonType": "int"
        },
        "alert_threshold": {
          "bsonType": "int",
          "minimum": 0,
          "maximum": 500
        },
        "status": {
          "enum": [
            "active",
            "paused",
            "expired"
          ]
        },
        "createdAt": {
          "bsonType": "date"
        },
        "updatedAt": {
          "bsonType": [
            "date",
            "null"
          ]
        },
        "last_triggered": {
          "bsonType": [
            "date",
            "null"
          ]
        },
        "email_count": {
          "bsonType": "int",
          "minimum": 0
        },
        "metadata": {
          "bsonType": "object"
        },
        "station_name": {
          "bsonType": "string"
        }
      }
    }
  }
});

// Create indexes for alert_subscriptions
db.alert_subscriptions.createIndex({"user_id": 1});
db.alert_subscriptions.createIndex({"station_id": 1});
db.alert_subscriptions.createIndex({"station_id": 1, "alert_threshold": 1, "status": 1});
db.alert_subscriptions.createIndex({"user_id": 1, "status": 1});


// Create collection: api_response_cache

db.createCollection("api_response_cache", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "key",
        "value",
        "createdAt",
        "expiresAt"
      ],
      "properties": {
        "key": {
          "bsonType": "string"
        },
        "value": {
          "bsonType": "object"
        },
        "createdAt": {
          "bsonType": "date"
        },
        "expiresAt": {
          "bsonType": "date"
        }
      }
    }
  }
});

// Create indexes for api_response_cache
db.api_response_cache.createIndex({"expiresAt": 1});


// Create collection: current_reading_checkpoints

db.createCollection("current_reading_checkpoints", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "timestamp",
        "created_at",
        "stats"
      ],
      "properties": {
        "timestamp": {
          "bsonType": "date"
        },
        "created_at": {
          "bsonType": "date"
        },
        "stats": {
          "bsonType": "object",
          "properties": {
            "total_stations": {
              "bsonType": "int"
            },
            "successful_stations": {
              "bsonType": "int"
            },
            "failed_stations": {
              "bsonType": "int"
            },
            "total_readings": {
              "bsonType": "int"
            },
            "failed_station_ids": {
              "bsonType": "array"
            }
          }
        }
      }
    }
  }
});

// Create indexes for current_reading_checkpoints


// Create collection: email_validation_cache

db.createCollection("email_validation_cache", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "email",
        "status",
        "createdAt",
        "expiresAt"
      ],
      "properties": {
        "email": {
          "bsonType": "string"
        },
        "status": {
          "enum": [
            "valid",
            "invalid",
            "unknown"
          ]
        },
        "reason": {
          "bsonType": "string"
        },
        "details": {
          "bsonType": "object"
        },
        "createdAt": {
          "bsonType": "date"
        },
        "expiresAt": {
          "bsonType": "date"
        }
      }
    }
  }
});

// Create indexes for email_validation_cache
db.email_validation_cache.createIndex({"email": 1}, { "unique": true });
db.email_validation_cache.createIndex({"expiresAt": 1});

// Create collection: jwt_blocklist

db.createCollection("jwt_blocklist", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "jti",
        "user_id",
        "token_type",
        "revokedAt"
      ],
      "properties": {
        "jti": {
          "bsonType": "string"
        },
        "user_id": {
          "bsonType": "string"
        },
        "token_type": {
          "enum": [
            "access",
            "refresh"
          ]
        },
        "revokedAt": {
          "bsonType": "date"
        }
      }
    }
  }
});

// Create indexes for jwt_blocklist


// Create collection: notification_logs

db.createCollection("notification_logs", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "user_id",
        "station_id",
        "sentAt",
        "status",
        "attempts"
      ],
      "properties": {
        "subscription_id": {
          "bsonType": [
            "objectId",
            "null"
          ]
        },
        "user_id": {
          "bsonType": "objectId"
        },
        "station_id": {
          "bsonType": "int"
        },
        "sentAt": {
          "bsonType": "date"
        },
        "status": {
          "enum": [
            "delivered",
            "failed",
            "deferred",
            "pending"
          ]
        },
        "attempts": {
          "bsonType": "int",
          "minimum": 0
        },
        "response": {
          "bsonType": "object"
        },
        "message_id": {
          "bsonType": [
            "string",
            "null"
          ]
        }
      }
    }
  }
});

// Create indexes for notification_logs
db.notification_logs.createIndex({"subscription_id": 1});
db.notification_logs.createIndex({"user_id": 1});
db.notification_logs.createIndex({"station_id": 1});
db.notification_logs.createIndex({"sentAt": 1});


// Create collection: password_resets

db.createCollection("password_resets", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "tokenHash",
        "user_id",
        "expiresAt",
        "createdAt"
      ],
      "properties": {
        "tokenHash": {
          "bsonType": "string"
        },
        "user_id": {
          "bsonType": "objectId"
        },
        "expiresAt": {
          "bsonType": "date"
        },
        "createdAt": {
          "bsonType": "date"
        },
        "used": {
          "bsonType": "bool"
        }
      }
    }
  }
});

// Create indexes for password_resets
db.password_resets.createIndex({"tokenHash": 1});
db.password_resets.createIndex({"expiresAt": 1});


// Create collection: users

db.createCollection("users", {
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": [
        "username",
        "email",
        "passwordHash",
        "role"
      ],
      "properties": {
        "username": {
          "bsonType": "string"
        },
        "email": {
          "bsonType": "string"
        },
        "passwordHash": {
          "bsonType": "string"
        },
        "role": {
          "enum": [
            "user",
            "admin"
          ]
        },
        "status": {
          "enum": [
            "active",
            "inactive"
          ]
        },
        "preferences": {
          "bsonType": "object",
          "properties": {
            "language": {
              "bsonType": "string"
            },
            "theme": {
              "enum": [
                "light",
                "dark"
              ]
            },
            "favoriteStations": {
              "bsonType": "array",
              "items": {
                "bsonType": "int"
              }
            },
            "defaultStation": {
              "bsonType": "int"
            },
            "notifications": {
              "bsonType": "object"
            }
          }
        },
        "createdAt": {
          "bsonType": "date"
        },
        "updatedAt": {
          "bsonType": "date"
        }
      }
    }
  }
});

// Create indexes for users
db.users.createIndex({"email": 1}, { "unique": true });
db.users.createIndex({"username": 1}, { "unique": true });

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




//////////////////////// SAMPLE QUERYS ////////////////////////
