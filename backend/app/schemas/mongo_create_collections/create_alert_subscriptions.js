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
