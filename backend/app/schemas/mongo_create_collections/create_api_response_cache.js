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
