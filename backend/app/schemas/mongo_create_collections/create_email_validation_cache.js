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
