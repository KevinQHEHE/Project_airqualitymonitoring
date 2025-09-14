"""
Forecast ingestion script for scheduled execution.

Purpose: Fetch daily forecast data for all stations and save to MongoDB.
Designed to be executed periodically by the scheduler infrastructure.

Usage:
    python ingest/get_forecast_data.py [--dry-run] [--log-level DEBUG]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from pymongo.errors import ConnectionFailure

from ingest.forecast_ingest import ForecastIngestionService, ForecastIngestError
from ingest.aqicn_client import create_client_from_env, AqicnClientError


def load_env_file():
    """Load environment variables manually from .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key] = value


def setup_logging(level: str = 'INFO') -> None:
    """Setup logging configuration."""
    log_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def main():
    """Main function to execute forecast ingestion."""
    parser = argparse.ArgumentParser(description='Fetch forecast data for all stations')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                        help='Set the logging level')
    
    args = parser.parse_args()
    
    # Load environment variables
    load_env_file()
    
    # Setup logging
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Starting forecast data ingestion")
        
        if args.dry_run:
            logger.info("DRY RUN MODE - No data will be saved to database")
        
        # Create API client
        try:
            api_client = create_client_from_env()
        except Exception as e:
            logger.error(f"Failed to create API client: {e}")
            return 1
        
        # Create forecast ingestion service
        try:
            forecast_service = ForecastIngestionService(client=api_client)
        except ForecastIngestError as e:
            logger.error(f"Failed to initialize forecast service: {e}")
            return 1
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to database: {e}")
            return 1
        
        # Execute forecast ingestion
        run_at = datetime.now(timezone.utc)
        
        try:
            if args.dry_run:
                # In dry run mode, just get station count and log
                station_ids = forecast_service.get_all_station_ids()
                logger.info(f"DRY RUN: Would process forecast data for {len(station_ids)} stations")
                
                # Sample first few stations for testing
                for idx, station_id in enumerate(station_ids[:3]):
                    logger.info(f"DRY RUN: Would fetch forecast data for station {station_id}")
                    
                if len(station_ids) > 3:
                    logger.info(f"DRY RUN: ... and {len(station_ids) - 3} more stations")
                
                return 0
            else:
                # Real ingestion
                results = forecast_service.ingest_all_station_forecasts(run_at=run_at)
                
                if results['success']:
                    logger.info(
                        f"Forecast ingestion completed successfully: "
                        f"{results['successful_stations']}/{results['total_stations']} stations, "
                        f"{results['total_forecasts_processed']} forecasts processed"
                    )
                    
                    # Log any failed stations
                    if results['failed_stations'] > 0:
                        logger.warning(f"{results['failed_stations']} stations failed during processing")
                        for station_result in results['stations_results']:
                            if not station_result['success']:
                                logger.warning(
                                    f"Station {station_result['station_idx']} failed: "
                                    f"{station_result.get('reason', 'Unknown error')}"
                                )
                    
                    return 0
                else:
                    logger.error(f"Forecast ingestion failed: {results.get('error', 'Unknown error')}")
                    return 1
                    
        except ForecastIngestError as e:
            logger.error(f"Forecast ingestion error: {e}")
            return 1
        except AqicnClientError as e:
            logger.error(f"API client error: {e}")
            return 1
        except Exception as e:
            logger.error(f"Unexpected error during forecast ingestion: {e}")
            return 1
        
    except KeyboardInterrupt:
        logger.info("Forecast ingestion interrupted by user")
        return 1
    except Exception as e:
        logger.error(f"Critical error: {e}")
        return 1
    finally:
        logger.info("Forecast ingestion script finished")


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)