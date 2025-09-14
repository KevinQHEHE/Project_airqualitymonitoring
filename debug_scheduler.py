"""
Debug script to test scheduler initialization
"""
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("Environment variables:")
print(f"STATION_POLLING_INTERVAL_MINUTES: {os.environ.get('STATION_POLLING_INTERVAL_MINUTES')}")
print(f"STATION_FORECAST_INTERVAL_MINUTES: {os.environ.get('STATION_FORECAST_INTERVAL_MINUTES')}")  
print(f"ENABLE_STATION_SCHEDULER: {os.environ.get('ENABLE_STATION_SCHEDULER')}")
print(f"ENABLE_FORECAST_SCHEDULER: {os.environ.get('ENABLE_FORECAST_SCHEDULER')}")

try:
    from ingest.streaming import DataIngestionScheduler
    
    print("\nCreating scheduler...")
    scheduler = DataIngestionScheduler()
    
    print(f"Station script path: {scheduler.station_script_path}")
    print(f"Forecast script path: {scheduler.forecast_script_path}")
    print(f"Station script exists: {os.path.exists(scheduler.station_script_path) if scheduler.station_script_path else 'None'}")
    print(f"Forecast script exists: {os.path.exists(scheduler.forecast_script_path) if scheduler.forecast_script_path else 'None'}")
    
    print(f"Station scheduler enabled: {scheduler.enable_station_scheduler}")
    print(f"Forecast scheduler enabled: {scheduler.enable_forecast_scheduler}")
    
    print("\nStarting scheduler...")
    success = scheduler.start()
    print(f"Start result: {success}")
    
    print("\nScheduler status:")
    status = scheduler.get_status()
    print(status)
    
    if scheduler.scheduler:
        print(f"\nScheduler jobs: {len(scheduler.scheduler.get_jobs())}")
        for job in scheduler.scheduler.get_jobs():
            print(f"  - {job.id}: {job.name} (next: {job.next_run_time})")
    
    print("\nStopping scheduler...")
    scheduler.stop()
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()