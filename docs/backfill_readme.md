# Backfill Job Documentation

## Overview

The backfill job (`/ingest/backfill.py`) loads multi-year historical air quality data for all Vietnamese stations from the AQICN API into MongoDB. It's designed to be resumable, efficient, and robust for long-running data collection tasks.

## Features

- **Resumable Execution**: Uses checkpoints to track progress per station
- **Configurable Time Range**: Default 2 years, customizable via command line
- **Batch Processing**: Processes data in configurable hourly windows (default: 1 week)
- **Rate Limiting**: Respects AQICN API limits with configurable delays
- **Error Handling**: Comprehensive error handling with detailed logging
- **Dry Run Mode**: Test execution without actual data insertion
- **Selective Processing**: Process specific stations or all stations

## Architecture

### Key Components

1. **BackfillJobManager**: Main orchestrator class
2. **BackfillCheckpoint**: Checkpoint data structure for resumability
3. **Data Transformation**: Converts AQICN API responses to MongoDB time-series format
4. **Batch Processing**: Handles large time ranges in manageable chunks

### Database Collections

- **Source**: `waqi_stations` - Station metadata
- **Target**: `waqi_station_readings` - Time-series air quality readings
- **Checkpoints**: `ingest_checkpoints` - Job state persistence

### Checkpoint Schema

```javascript
{
  "station_idx": 12345,
  "last_processed_ts": ISODate("2023-01-01T00:00:00Z"),
  "start_ts": ISODate("2021-09-10T00:00:00Z"),
  "target_end_ts": ISODate("2025-09-10T00:00:00Z"),
  "total_hours_processed": 15000,
  "total_readings_inserted": 8742,
  "last_updated": ISODate("2025-09-10T10:30:00Z"),
  "status": "in_progress",  // "in_progress", "completed", "failed"
  "error_message": null
}
```

## Usage

### Basic Usage

```bash
# Backfill all stations with default settings (2 years)
python -m ingest.backfill

# Dry run to test without inserting data
python -m ingest.backfill --dry-run

# Process specific stations only
python -m ingest.backfill --stations 12345 67890 11111

# Custom time range (3 years)
python -m ingest.backfill --years 3

# Custom batch size (1 day instead of 1 week)
python -m ingest.backfill --batch-size 24

# Faster rate limiting (2 seconds between requests)
python -m ingest.backfill --rate-limit 2

# Debug logging
python -m ingest.backfill --log-level DEBUG
```

### Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--stations` | Specific station IDs to process | All stations |
| `--start-date` | Start date (YYYY-MM-DD) override | 2 years ago |
| `--years` | Years of historical data to fetch | 2 |
| `--batch-size` | Hours to process per batch | 168 (1 week) |
| `--rate-limit` | Delay between API requests (seconds) | 4 |
| `--dry-run` | Run without inserting data | False |
| `--log-level` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |

## Environment Variables

Required environment variables (typically in `.env` file):

```bash
# MongoDB connection
MONGO_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGO_DB=air_quality_db

# AQICN API credentials
AQICN_API_KEY=your_api_key_here
```

## Data Flow

### 1. Station Discovery
```python
# Fetch all stations from waqi_stations collection
stations = db.waqi_stations.find({}, {
    '_id': 1,
    'city.name': 1, 
    'city.geo.coordinates': 1,
    'time.tz': 1
})
```

### 2. Checkpoint Management
```python
# Check existing checkpoint
checkpoint = db.ingest_checkpoints.find_one({'station_idx': station_id})

# Create new checkpoint if not exists
if not checkpoint:
    checkpoint = {
        'station_idx': station_id,
        'last_processed_ts': start_time,
        'start_ts': start_time,
        'target_end_ts': end_time,
        'status': 'in_progress'
    }
```

### 3. Batch Processing
```python
# Process in hourly windows
while current_time < target_end_time:
    batch_end = min(current_time + batch_size_hours, target_end_time)
    
    # Fetch data from AQICN API
    readings = fetch_historical_batch(station_id, current_time, batch_end)
    
    # Upsert to MongoDB
    upsert_readings_bulk(readings_collection, readings)
    
    # Update checkpoint
    update_checkpoint(station_id, batch_end)
    
    current_time = batch_end
```

### 4. Data Transformation

AQICN API responses are transformed to match the `waqi_station_readings` time-series schema:

```python
# Input: AQICN API response
{
    "current_aqi": 45,
    "time": {"s": "2023-01-01 12:00:00", "tz": "+07:00"},
    "current_iaqi": {"pm25": {"v": 45}, "pm10": {"v": 32}}
}

# Output: MongoDB document
{
    "ts": ISODate("2023-01-01T05:00:00Z"),  # UTC
    "meta": {"station_idx": 12345},
    "aqi": 45,
    "time": {"s": "2023-01-01 12:00:00", "tz": "+07:00"},
    "iaqi": {"pm25": {"v": 45}, "pm10": {"v": 32}}
}
```

## Monitoring & Logging

### Log Levels

- **DEBUG**: Detailed API requests and data processing
- **INFO**: Progress updates and major operations
- **WARNING**: Recoverable errors and missing data
- **ERROR**: Fatal errors and failures

### Progress Tracking

The job logs progress at multiple levels:

```
2025-09-10 10:30:00 - INFO - Starting backfill for 35 stations
2025-09-10 10:30:05 - INFO - Processing station 1/35: 12345
2025-09-10 10:30:10 - DEBUG - Station 12345 progress: 25.3%
2025-09-10 10:35:00 - INFO - Progress: 10/35 stations processed
2025-09-10 11:00:00 - INFO - Completed backfill for station 12345: 2847 readings
```

### Error Handling

- **API Errors**: Logged but don't stop processing other stations
- **Database Errors**: Mark station as failed and continue
- **Rate Limiting**: Automatic retry with exponential backoff
- **Interrupt Handling**: Graceful shutdown with checkpoint saving

## Performance Considerations

### Batch Size Tuning

- **Small batches (24 hours)**: More API requests, more granular checkpoints
- **Large batches (1 week)**: Fewer API requests, less granular recovery
- **Memory usage**: Scales with batch size × number of pollutants

### Rate Limiting

- **AQICN API limit**: 1000 requests/hour
- **Default delay**: 4 seconds between requests (≈900 requests/hour)
- **Recommended**: Monitor API usage and adjust as needed

### Database Performance

- **Upsert strategy**: Uses `(station_idx, ts)` compound key
- **Bulk operations**: Processes readings in batches for efficiency
- **Indexes**: Ensure proper indexes on time-series collection

## Resumability

The job is fully resumable at any point:

1. **Graceful shutdown**: Saves checkpoints before exit
2. **Crash recovery**: Resumes from last saved checkpoint
3. **Partial completion**: Completed stations are skipped on restart
4. **Failed stations**: Can be retried by resetting their status

### Resetting Failed Stations

```javascript
// Reset a failed station for retry
db.ingest_checkpoints.updateOne(
    {station_idx: 12345, status: "failed"},
    {$set: {status: "in_progress", error_message: null}}
)

// Reset all failed stations
db.ingest_checkpoints.updateMany(
    {status: "failed"},
    {$set: {status: "in_progress", error_message: null}}
)
```

## Validation

### Data Quality Checks

1. **Required fields**: `ts`, `meta.station_idx`, `aqi` must be present
2. **Time validation**: Timestamps must be valid and within expected range
3. **AQI validation**: AQI values should be non-negative integers
4. **Deduplication**: Same timestamp for same station is upserted

### Sample Validation Query

```javascript
// Check backfilled data for a station
db.waqi_station_readings.find({
    "meta.station_idx": 12345,
    "ts": {
        $gte: ISODate("2023-09-10T00:00:00Z"),
        $lte: ISODate("2025-09-10T00:00:00Z")
    }
}).sort({"ts": -1}).limit(10)
```

## Troubleshooting

### Common Issues

1. **API Rate Limiting**
   - Symptoms: `AqicnRateLimitError` exceptions
   - Solution: Increase `--rate-limit` delay

2. **Missing Environment Variables**
   - Symptoms: Connection errors on startup
   - Solution: Verify `.env` file and required variables

3. **Network Timeouts**
   - Symptoms: Timeout errors for specific stations
   - Solution: These are automatically retried; check station data availability

4. **Memory Usage**
   - Symptoms: High memory consumption
   - Solution: Reduce `--batch-size` parameter

### Recovery Procedures

1. **Check job status**:
   ```javascript
   db.ingest_checkpoints.aggregate([
       {$group: {
           _id: "$status", 
           count: {$sum: 1}
       }}
   ])
   ```

2. **Restart failed stations**:
   ```bash
   python -m ingest.backfill --stations 12345 67890
   ```

3. **Full restart** (if needed):
   ```javascript
   db.ingest_checkpoints.deleteMany({})
   ```

## Expected Outputs

### Successful Execution

```
===============================================================================
BACKFILL JOB SUMMARY
===============================================================================
Total stations: 35
Completed stations: 35
Failed stations: 0
Skipped stations: 0
Total readings inserted: 125,847
Total API requests: 1,750
Duration: 2:15:30
Success rate: 100.0%
===============================================================================
```

### Generated Collections

1. **waqi_station_readings**: Historical air quality data
2. **ingest_checkpoints**: Job state and progress tracking
3. **Log file**: `backfill.log` with detailed execution log

## Integration

### With Existing System

The backfill job integrates seamlessly with the existing air quality monitoring system:

- Uses same MongoDB collections and schema
- Compatible with existing API endpoints
- Works alongside real-time data ingestion
- Supports same query patterns and indexes

### Next Steps

After successful backfill:

1. **Verify data quality**: Run validation queries
2. **Create indexes**: Ensure optimal query performance
3. **Update dashboards**: Historical data now available for analysis
4. **Schedule maintenance**: Periodic cleanup of old checkpoints
