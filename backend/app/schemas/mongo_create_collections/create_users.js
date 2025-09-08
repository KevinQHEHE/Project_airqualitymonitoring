// users
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
        "_id": {
          "bsonType": "objectId"
        },
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
        "location": {
          "bsonType": "object",
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
            "notifications": {}
          },
          "additionalProperties": false
        },
        "createdAt": {
          "bsonType": "date"
        },
        "updatedAt": {
          "bsonType": "date"
        }
      },
      "additionalProperties": false
    }
  }
});

db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ username: 1 }, { unique: true });
db.users.createIndex({ location: "2dsphere" });
