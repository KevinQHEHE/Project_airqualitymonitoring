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
