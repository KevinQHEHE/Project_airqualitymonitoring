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
