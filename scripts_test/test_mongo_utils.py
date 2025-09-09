"""Unit tests for MongoDB upsert utilities.

Tests validate idempotent behavior, bulk operations, error handling,
and data integrity for stations, readings, and forecasts upserts.
"""

from __future__ import annotations

import unittest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from pymongo.errors import BulkWriteError, PyMongoError
from pymongo.results import UpdateResult, BulkWriteResult

# Import the functions to test
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from ingest.mongo_utils import (
    upsert_station,
    upsert_readings,
    upsert_forecasts,
    bulk_upsert_stations,
    MongoUpsertError
)


class TestUpsertStation(unittest.TestCase):
    """Test cases for station upsert operations."""
    
    def test_upsert_station_success_insert(self):
        """Test successful station insertion."""
        # Mock collection
        mock_collection = Mock()
        mock_result = Mock(spec=UpdateResult)
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_id = 1001
        mock_result.acknowledged = True
        mock_collection.replace_one.return_value = mock_result
        
        # Sample station data
        station_data = {
            '_id': 1001,
            'city': {
                'name': 'Test City',
                'url': 'test-city',
                'geo': {
                    'type': 'Point',
                    'coordinates': [106.7, 10.8]
                }
            },
            'tz': '+07:00'
        }
        
        # Execute upsert
        result = upsert_station(mock_collection, station_data)
        
        # Verify
        mock_collection.replace_one.assert_called_once_with(
            {'_id': 1001},
            station_data,
            upsert=True
        )
        self.assertEqual(result['station_id'], 1001)
        self.assertEqual(result['matched_count'], 0)
        self.assertEqual(result['upserted_id'], 1001)
        self.assertTrue(result['acknowledged'])
    
    def test_upsert_station_success_update(self):
        """Test successful station update."""
        # Mock collection
        mock_collection = Mock()
        mock_result = Mock(spec=UpdateResult)
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_id = None
        mock_result.acknowledged = True
        mock_collection.replace_one.return_value = mock_result
        
        station_data = {
            '_id': 1001,
            'city': {
                'name': 'Updated City',
                'url': 'updated-city',
                'geo': {
                    'type': 'Point',
                    'coordinates': [106.8, 10.9]
                }
            }
        }
        
        result = upsert_station(mock_collection, station_data)
        
        self.assertEqual(result['station_id'], 1001)
        self.assertEqual(result['matched_count'], 1)
        self.assertEqual(result['modified_count'], 1)
        self.assertIsNone(result['upserted_id'])
    
    def test_upsert_station_missing_id(self):
        """Test error when _id field is missing."""
        mock_collection = Mock()
        station_data = {
            'city': {
                'name': 'Test City',
                'url': 'test-city'
            }
        }
        
        with self.assertRaises(ValueError) as context:
            upsert_station(mock_collection, station_data)
        self.assertIn("Station data must contain '_id' field", str(context.exception))
    
    def test_upsert_station_missing_city(self):
        """Test error when city field is missing."""
        mock_collection = Mock()
        station_data = {
            '_id': 1001
        }
        
        with self.assertRaises(ValueError) as context:
            upsert_station(mock_collection, station_data)
        self.assertIn("Station data must contain 'city' field", str(context.exception))
    
    def test_upsert_station_mongo_error(self):
        """Test handling of MongoDB errors."""
        mock_collection = Mock()
        mock_collection.replace_one.side_effect = PyMongoError("Connection failed")
        
        station_data = {
            '_id': 1001,
            'city': {
                'name': 'Test City',
                'url': 'test-city'
            }
        }
        
        with self.assertRaises(MongoUpsertError) as context:
            upsert_station(mock_collection, station_data)
        self.assertIn("Station upsert failed", str(context.exception))


class TestUpsertReadings(unittest.TestCase):
    """Test cases for readings upsert operations."""
    
    def test_upsert_readings_success(self):
        """Test successful readings bulk upsert."""
        # Mock collection
        mock_collection = Mock()
        mock_result = Mock(spec=BulkWriteResult)
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_count = 2
        mock_result.acknowledged = True
        mock_collection.bulk_write.return_value = mock_result
        
        # Sample readings data
        readings = [
            {
                'ts': '2025-09-09T10:00:00Z',
                'aqi': 85,
                'time': {
                    's': '2025-09-09 17:00:00',
                    'tz': '+07:00'
                }
            },
            {
                'ts': '2025-09-09T11:00:00Z',
                'aqi': 92,
                'time': {
                    's': '2025-09-09 18:00:00',
                    'tz': '+07:00'
                }
            },
            {
                'ts': '2025-09-09T10:00:00Z',  # Duplicate timestamp (should update)
                'aqi': 88,
                'time': {
                    's': '2025-09-09 17:00:00',
                    'tz': '+07:00'
                }
            }
        ]
        
        # Execute upsert
        result = upsert_readings(mock_collection, 1001, readings)
        
        # Verify bulk_write was called
        mock_collection.bulk_write.assert_called_once()
        call_args = mock_collection.bulk_write.call_args[0][0]  # First positional arg (operations)
        
        # Verify operations structure
        self.assertEqual(len(call_args), 3)
        
        # Check that meta.station_idx was added to all readings
        for i, operation in enumerate(call_args):
            filter_query = operation._filter
            update_doc = operation._doc['$set']
            
            self.assertEqual(filter_query['meta.station_idx'], 1001)
            self.assertEqual(filter_query['ts'], readings[i]['ts'])
            self.assertEqual(update_doc['meta']['station_idx'], 1001)
            self.assertEqual(update_doc['aqi'], readings[i]['aqi'])
        
        # Verify result
        self.assertEqual(result['station_idx'], 1001)
        self.assertEqual(result['processed_count'], 3)
        self.assertEqual(result['upserted_count'], 2)
        self.assertEqual(result['modified_count'], 1)
    
    def test_upsert_readings_empty_list(self):
        """Test handling of empty readings list."""
        mock_collection = Mock()
        
        result = upsert_readings(mock_collection, 1001, [])
        
        # Should not call bulk_write
        mock_collection.bulk_write.assert_not_called()
        self.assertEqual(result['station_idx'], 1001)
        self.assertEqual(result['processed_count'], 0)
    
    def test_upsert_readings_missing_ts(self):
        """Test error when ts field is missing."""
        mock_collection = Mock()
        readings = [
            {
                'aqi': 85,
                'time': {'s': '2025-09-09 17:00:00', 'tz': '+07:00'}
            }
        ]
        
        with self.assertRaises(ValueError) as context:
            upsert_readings(mock_collection, 1001, readings)
        self.assertIn("Reading must contain 'ts' field", str(context.exception))
    
    def test_upsert_readings_bulk_write_error(self):
        """Test handling of bulk write errors."""
        mock_collection = Mock()
        mock_collection.bulk_write.side_effect = BulkWriteError({"writeErrors": []})
        
        readings = [
            {
                'ts': '2025-09-09T10:00:00Z',
                'aqi': 85,
                'time': {'s': '2025-09-09 17:00:00', 'tz': '+07:00'}
            }
        ]
        
        with self.assertRaises(MongoUpsertError) as context:
            upsert_readings(mock_collection, 1001, readings)
        self.assertIn("Readings bulk upsert failed", str(context.exception))


class TestUpsertForecasts(unittest.TestCase):
    """Test cases for forecasts upsert operations."""
    
    def test_upsert_forecasts_success(self):
        """Test successful forecasts bulk upsert."""
        # Mock collection
        mock_collection = Mock()
        mock_result = Mock(spec=BulkWriteResult)
        mock_result.matched_count = 0
        mock_result.modified_count = 0
        mock_result.upserted_count = 2
        mock_result.acknowledged = True
        mock_collection.bulk_write.return_value = mock_result
        
        # Sample forecasts data
        forecasts = [
            {
                'day': '2025-09-10',
                'pollutants': {
                    'pm25': {'avg': 45, 'min': 30, 'max': 60},
                    'pm10': {'avg': 55, 'min': 40, 'max': 70}
                }
            },
            {
                'day': '2025-09-11',
                'pollutants': {
                    'pm25': {'avg': 50, 'min': 35, 'max': 65}
                }
            }
        ]
        
        # Execute upsert
        result = upsert_forecasts(mock_collection, 1001, forecasts)
        
        # Verify bulk_write was called
        mock_collection.bulk_write.assert_called_once()
        call_args = mock_collection.bulk_write.call_args[0][0]
        
        # Verify operations structure
        self.assertEqual(len(call_args), 2)
        
        for i, operation in enumerate(call_args):
            filter_query = operation._filter
            update_doc = operation._doc['$set']
            
            self.assertEqual(filter_query['station_idx'], 1001)
            self.assertEqual(filter_query['day'], forecasts[i]['day'])
            self.assertEqual(update_doc['station_idx'], 1001)
            self.assertEqual(update_doc['day'], forecasts[i]['day'])
            self.assertEqual(update_doc['pollutants'], forecasts[i]['pollutants'])
        
        # Verify result
        self.assertEqual(result['station_idx'], 1001)
        self.assertEqual(result['processed_count'], 2)
        self.assertEqual(result['upserted_count'], 2)
    
    def test_upsert_forecasts_missing_day(self):
        """Test error when day field is missing."""
        mock_collection = Mock()
        forecasts = [
            {
                'pollutants': {
                    'pm25': {'avg': 45, 'min': 30, 'max': 60}
                }
            }
        ]
        
        with self.assertRaises(ValueError) as context:
            upsert_forecasts(mock_collection, 1001, forecasts)
        self.assertIn("Forecast must contain 'day' field", str(context.exception))
    
    def test_upsert_forecasts_missing_pollutants(self):
        """Test error when pollutants field is missing."""
        mock_collection = Mock()
        forecasts = [
            {
                'day': '2025-09-10'
            }
        ]
        
        with self.assertRaises(ValueError) as context:
            upsert_forecasts(mock_collection, 1001, forecasts)
        self.assertIn("Forecast must contain 'pollutants' field", str(context.exception))


class TestBulkUpsertStations(unittest.TestCase):
    """Test cases for bulk station upsert operations."""
    
    def test_bulk_upsert_stations_success(self):
        """Test successful bulk stations upsert."""
        # Mock collection
        mock_collection = Mock()
        mock_result = Mock(spec=BulkWriteResult)
        mock_result.matched_count = 1
        mock_result.modified_count = 1
        mock_result.upserted_count = 2
        mock_result.acknowledged = True
        mock_collection.bulk_write.return_value = mock_result
        
        # Sample stations data
        stations = [
            {
                '_id': 1001,
                'city': {
                    'name': 'Ho Chi Minh City',
                    'url': 'ho-chi-minh-city',
                    'geo': {'type': 'Point', 'coordinates': [106.7, 10.8]}
                }
            },
            {
                '_id': 1002,
                'city': {
                    'name': 'Hanoi',
                    'url': 'hanoi',
                    'geo': {'type': 'Point', 'coordinates': [105.8, 21.0]}
                }
            },
            {
                '_id': 1001,  # Duplicate (should update)
                'city': {
                    'name': 'Ho Chi Minh City Updated',
                    'url': 'ho-chi-minh-city-updated',
                    'geo': {'type': 'Point', 'coordinates': [106.7, 10.8]}
                }
            }
        ]
        
        # Execute bulk upsert
        result = bulk_upsert_stations(mock_collection, stations)
        
        # Verify bulk_write was called
        mock_collection.bulk_write.assert_called_once()
        call_args = mock_collection.bulk_write.call_args[0][0]
        
        # Verify operations structure
        self.assertEqual(len(call_args), 3)
        
        for i, operation in enumerate(call_args):
            filter_query = operation._filter
            update_doc = operation._doc['$set']
            
            self.assertEqual(filter_query['_id'], stations[i]['_id'])
            self.assertEqual(update_doc, stations[i])
        
        # Verify result
        self.assertEqual(result['processed_count'], 3)
        self.assertEqual(result['upserted_count'], 2)
        self.assertEqual(result['modified_count'], 1)
    
    def test_bulk_upsert_stations_empty_list(self):
        """Test handling of empty stations list."""
        mock_collection = Mock()
        
        result = bulk_upsert_stations(mock_collection, [])
        
        # Should not call bulk_write
        mock_collection.bulk_write.assert_not_called()
        self.assertEqual(result['processed_count'], 0)
    
    def test_bulk_upsert_stations_missing_id(self):
        """Test error when _id field is missing."""
        mock_collection = Mock()
        stations = [
            {
                'city': {
                    'name': 'Test City',
                    'url': 'test-city'
                }
            }
        ]
        
        with self.assertRaises(ValueError) as context:
            bulk_upsert_stations(mock_collection, stations)
        self.assertIn("Station must contain '_id' field", str(context.exception))


class TestIdempotentBehavior(unittest.TestCase):
    """Integration tests for idempotent behavior validation."""
    
    def test_station_idempotent_runs(self):
        """Test that repeated station upserts are idempotent."""
        mock_collection = Mock()
        
        # First run - insert
        mock_result_1 = Mock(spec=UpdateResult)
        mock_result_1.matched_count = 0
        mock_result_1.modified_count = 0
        mock_result_1.upserted_id = 1001
        mock_result_1.acknowledged = True
        
        # Second run - no change
        mock_result_2 = Mock(spec=UpdateResult)
        mock_result_2.matched_count = 1
        mock_result_2.modified_count = 0  # No modification needed
        mock_result_2.upserted_id = None
        mock_result_2.acknowledged = True
        
        mock_collection.replace_one.side_effect = [mock_result_1, mock_result_2]
        
        station_data = {
            '_id': 1001,
            'city': {
                'name': 'Test City',
                'url': 'test-city',
                'geo': {'type': 'Point', 'coordinates': [106.7, 10.8]}
            }
        }
        
        # First run
        result1 = upsert_station(mock_collection, station_data)
        self.assertEqual(result1['upserted_id'], 1001)
        
        # Second run (idempotent)
        result2 = upsert_station(mock_collection, station_data)
        self.assertEqual(result2['matched_count'], 1)
        self.assertEqual(result2['modified_count'], 0)
        self.assertIsNone(result2['upserted_id'])
        
        # Verify both calls used same filter and data
        self.assertEqual(mock_collection.replace_one.call_count, 2)
        for call in mock_collection.replace_one.call_args_list:
            args, kwargs = call
            self.assertEqual(args[0], {'_id': 1001})
            self.assertEqual(args[1], station_data)
            self.assertTrue(kwargs['upsert'])


if __name__ == '__main__':
    # Run tests if script is executed directly
    unittest.main(verbosity=2)
