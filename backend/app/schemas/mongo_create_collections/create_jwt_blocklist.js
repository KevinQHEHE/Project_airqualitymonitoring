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
