# MongoDB Schema Files - Usage Guide

## Overview

This directory contains MongoDB schema definitions for the Air Quality Monitoring system database. The schemas are organized into three categories:

1. **MongoDB Validators** (`mongo_validators/`) - Server-side validation schemas
2. **JSON Schemas** (`schemas_jsonschema/`) - Application-level validation schemas  
3. **Create Scripts** (`mongo_create_collections/`) - MongoDB shell scripts to create collections with validators and indexes

## Directory Structure

```
backend/app/schemas/
├── mongo_validators/           # MongoDB $jsonSchema validators
│   ├── users.validator.json
│   ├── waqi_stations.validator.json
│   ├── waqi_station_readings.validator.json
│   ├── waqi_daily_forecasts.validator.json
│   ├── alert_subscriptions.validator.json
│   ├── notification_logs.validator.json
│   ├── password_resets.validator.json
│   ├── email_validation_cache.validator.json
│   ├── jwt_blocklist.validator.json
│   ├── current_reading_checkpoints.validator.json
│   └── api_response_cache.validator.json
│
├── schemas_jsonschema/         # JSON Schema (Draft 7) files
│   ├── users.schema.json
│   ├── waqi_stations.schema.json
│   ├── waqi_station_readings.schema.json
│   ├── waqi_daily_forecasts.schema.json
│   ├── alert_subscriptions.schema.json
│   ├── notification_logs.schema.json
│   ├── password_resets.schema.json
│   ├── email_validation_cache.schema.json
│   ├── jwt_blocklist.schema.json
│   ├── current_reading_checkpoints.schema.json
│   ├── api_response_cache.schema.json
│   └── stations_list.response.json
│
└── mongo_create_collections/   # MongoDB creation scripts
    ├── create_users.js
    ├── create_waqi_stations.js
    ├── create_waqi_station_readings.js
    ├── create_waqi_daily_forecasts.js
    ├── create_alert_subscriptions.js
    ├── create_notification_logs.js
    ├── create_password_resets.js
    ├── create_email_validation_cache.js
    ├── create_jwt_blocklist.js
    ├── create_current_reading_checkpoints.js
    └── create_api_response_cache.js
```

## Schema Types

### 1. MongoDB Validators (`mongo_validators/`)

**Purpose**: Server-side validation enforced by MongoDB  
**Format**: MongoDB $jsonSchema  
**Usage**: Applied when creating collections or via `db.runCommand({collMod: ...})`

**Example**:
```json
{
  "validator": {
    "$jsonSchema": {
      "bsonType": "object",
      "required": ["username", "email", "passwordHash", "role"],
      "properties": {
        "username": {"bsonType": "string"},
        "email": {"bsonType": "string"},
        "role": {"enum": ["user", "admin"]}
      }
    }
  }
}
```

### 2. JSON Schemas (`schemas_jsonschema/`)

**Purpose**: Application-level validation (Python, Node.js, etc.)  
**Format**: JSON Schema Draft 7  
**Usage**: Validate data before inserting/updating in application code

**Example**:
```python
from jsonschema import validate
import json

# Load schema
with open('schemas_jsonschema/users.schema.json') as f:
    schema = json.load(f)

# Validate data
user_data = {
    "username": "john_doe",
    "email": "john@example.com",
    "passwordHash": "$2b$12$...",
    "role": "user"
}

validate(instance=user_data, schema=schema)
```

### 3. Create Scripts (`mongo_create_collections/`)

**Purpose**: Initialize database collections with validators and indexes  
**Format**: MongoDB JavaScript  
**Usage**: Run in MongoDB Shell or MongoDB Compass

**Example**:
```javascript
// In MongoDB Shell
use air_quality_db
load('create_users.js')
```

## Using the Schemas

### Method 1: Create New Database

To set up a new database with all collections, validators, and indexes:

```bash
# Using MongoDB Shell
mongosh "mongodb://localhost:27017/air_quality_db" \
  --file create_users.js \
  --file create_waqi_stations.js \
  --file create_waqi_station_readings.js \
  # ... (all create scripts)
```

Or use the helper script:
```bash
cd scripts
python create_all_collections.py
```

### Method 2: Add Validators to Existing Collections

```javascript
// In MongoDB Shell
use air_quality_db

// Load validator
var validator = <paste validator JSON here>

// Apply to collection
db.runCommand({
  collMod: "users",
  validator: validator.validator,
  validationLevel: "moderate"  // or "strict"
})
```

### Method 3: Python Application Validation

```python
from jsonschema import validate, ValidationError
import json

class UserSchema:
    def __init__(self):
        with open('backend/app/schemas/schemas_jsonschema/users.schema.json') as f:
            self.schema = json.load(f)
    
    def validate(self, data):
        try:
            validate(instance=data, schema=self.schema)
            return True, None
        except ValidationError as e:
            return False, str(e)

# Usage
user_schema = UserSchema()
is_valid, error = user_schema.validate(user_data)
if not is_valid:
    print(f"Validation error: {error}")
```

## Schema Validation Levels

MongoDB supports three validation levels:

1. **strict** (default): Validates all inserts and updates
2. **moderate**: Validates inserts and updates to existing valid documents
3. **off**: No validation (validator exists but not enforced)

```javascript
// Change validation level
db.runCommand({
  collMod: "users",
  validationLevel: "moderate"
})
```

## Special Collections

### Timeseries Collection: waqi_station_readings

This collection uses MongoDB's timeseries feature for optimized time-series data storage:

```javascript
db.createCollection("waqi_station_readings", {
  timeseries: {
    timeField: "ts",        // Field containing timestamp
    metaField: "meta",      // Field containing metadata
    granularity: "hours"    // Data granularity
  }
})
```

**Benefits**:
- Automatic data bucketing
- Improved compression
- Optimized time-range queries
- Reduced storage footprint

### TTL Collections

Collections with automatic document expiration:

- `password_resets` - Expires after date in `expiresAt` field
- `email_validation_cache` - Expires after date in `expiresAt` field  
- `api_response_cache` - Expires after date in `expiresAt` field

```javascript
// TTL index example
db.password_resets.createIndex(
  { "expiresAt": 1 },
  { expireAfterSeconds: 0 }
)
```

## Geospatial Collections

Collections with geospatial indexes for location-based queries:

- `waqi_stations` - 2dsphere index on `city.geo`
- `waqi_station_readings` - 2dsphere index on `location`

```javascript
// Example geospatial query
db.waqi_stations.find({
  "city.geo": {
    $near: {
      $geometry: {
        type: "Point",
        coordinates: [106.7, 10.8]  // [longitude, latitude]
      },
      $maxDistance: 5000  // meters
    }
  }
})
```

## Updating Schemas

### When Database Structure Changes

1. **Analyze the database**:
   ```bash
   python scripts/read_database_structure.py
   ```

2. **Regenerate schemas**:
   ```bash
   python scripts/generate_schemas_and_validators.py
   ```

3. **Verify changes**:
   ```bash
   python scripts/verify_schemas.py
   python scripts/compare_schemas.py
   ```

4. **Update validators on existing collections**:
   ```javascript
   // Load new validator
   var newValidator = <paste new validator>
   
   // Update collection
   db.runCommand({
     collMod: "collection_name",
     validator: newValidator.validator
   })
   ```

## Schema Maintenance Scripts

Located in `scripts/`:

- `read_database_structure.py` - Analyze database and generate structure report
- `generate_schemas_and_validators.py` - Generate all schema files from database
- `verify_schemas.py` - Verify all schema files exist and are valid
- `compare_schemas.py` - Compare schemas with actual database structure
- `list_databases.py` - List all databases and collections

## Best Practices

1. **Always validate in application layer first**: Use JSON schemas before writing to database
2. **Use moderate validation level**: Prevents invalid new data while allowing migrations
3. **Test validators before applying**: Use `db.runCommand()` with `validationAction: "warn"` first
4. **Version your schemas**: Keep schemas in version control with database migrations
5. **Document field purposes**: Add descriptions to schema properties
6. **Use indexes wisely**: Balance query performance with write overhead
7. **Review regularly**: Regenerate schemas periodically to catch drift

## Common Issues

### Issue: Validation Error on Insert

```
WriteError: Document failed validation
```

**Solution**: 
1. Check the validator definition
2. Ensure all required fields are present
3. Verify field types match
4. Use `validationLevel: "moderate"` during migrations

### Issue: Schema Mismatch

**Solution**:
```bash
# Compare schemas with database
python scripts/compare_schemas.py

# Regenerate if needed
python scripts/generate_schemas_and_validators.py
```

### Issue: Cannot Create Index

```
Error: Index creation failed
```

**Solution**:
1. Check for existing index with same name
2. Ensure sufficient resources
3. For large collections, create indexes in background

```javascript
db.collection.createIndex(
  { field: 1 },
  { background: true }  // Don't block other operations
)
```

## Additional Resources

- [MongoDB Schema Validation](https://docs.mongodb.com/manual/core/schema-validation/)
- [JSON Schema Specification](https://json-schema.org/specification.html)
- [MongoDB Timeseries Collections](https://docs.mongodb.com/manual/core/timeseries-collections/)
- [MongoDB Geospatial Queries](https://docs.mongodb.com/manual/geospatial-queries/)
- [MongoDB TTL Indexes](https://docs.mongodb.com/manual/core/index-ttl/)

## Support

For questions or issues:
1. Check the [DATABASE_SCHEMA_SUMMARY.md](../../docs/DATABASE_SCHEMA_SUMMARY.md) documentation
2. Review existing issues in the repository
3. Contact the development team

---

**Last Updated**: October 7, 2025  
**Database Version**: MongoDB 7.x (Atlas)  
**Schema Version**: 1.0.0
