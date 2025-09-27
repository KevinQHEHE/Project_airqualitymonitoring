"""
Background scheduler for periodic station reading and forecast data ingestion.

Purpose: Run get_station_reading.py and get_forecast_data.py scripts periodically via configurable schedules.
Uses APScheduler for robust job scheduling with proper shutdown handling.
Integrates with Flask app lifecycle for startup/teardown.

Key decisions:
- Uses BackgroundScheduler for non-blocking operation
- Subprocess execution for isolation from main Flask process
- Separate configurable intervals for station readings and forecasts
- Graceful shutdown with Flask teardown handlers

Extension points:
- Additional scheduled jobs can be added to the same scheduler
- Job persistence can be added for production deployments
"""
from __future__ import annotations

import atexit
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR
try:
    # Import monitoring function lazily to avoid circular import when running scripts
    from backend.app.tasks.alerts import monitor_favorite_stations
except Exception:
    monitor_favorite_stations = None

logger = logging.getLogger(__name__)

class DataIngestionScheduler:
    """
    Background scheduler for periodic station reading and forecast data ingestion.
    
    Features:
    - Separate configurable polling intervals for readings and forecasts
    - Subprocess execution for script isolation
    - Graceful shutdown handling
    - Job execution logging and error handling
    """
    
    def __init__(self, app=None):
        """
        Initialize the scheduler.
        
        Args:
            app: Flask application instance (optional)
        """
        self.app = app
        self.scheduler: Optional[BackgroundScheduler] = None
        self.is_running = False
        self._shutdown_event = threading.Event()
        
        # Station reading configuration
        self.station_polling_interval_minutes = int(os.environ.get('STATION_POLLING_INTERVAL_MINUTES', '60'))
        self.station_script_timeout_seconds = int(os.environ.get('STATION_SCRIPT_TIMEOUT_SECONDS', '300'))
        self.enable_station_scheduler = os.environ.get('ENABLE_STATION_SCHEDULER', 'true').lower() in ['true', '1', 'on', 'yes']
        
        # Forecast ingestion configuration
        forecast_env_value = os.environ.get('STATION_FORECAST_INTERVAL_MINUTES', '1440')
        print(f"=== DEBUG: STATION_FORECAST_INTERVAL_MINUTES environment value = '{forecast_env_value}' ===")
        self.forecast_polling_interval_minutes = int(forecast_env_value)  # Default 24 hours
        self.forecast_script_timeout_seconds = int(os.environ.get('FORECAST_SCRIPT_TIMEOUT_SECONDS', '600'))
        self.enable_forecast_scheduler = os.environ.get('ENABLE_FORECAST_SCHEDULER', 'true').lower() in ['true', '1', 'on', 'yes']
        print(f"=== DEBUG: Forecast scheduler will run every {self.forecast_polling_interval_minutes} minutes ===")
        
        # Script paths
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # Handle case where we're running from different contexts
        script_candidates = [
            os.path.join(project_root, 'ingest', 'get_station_reading.py'),
            os.path.join(os.path.dirname(project_root), 'ingest', 'get_station_reading.py'),
            os.path.join(os.getcwd(), 'ingest', 'get_station_reading.py'),
        ]
        
        self.station_script_path = None
        for candidate in script_candidates:
            if os.path.exists(candidate):
                self.station_script_path = candidate
                break
        
        if not self.station_script_path:
            self.station_script_path = script_candidates[0]  # Default fallback
        
        # Forecast script path
        forecast_candidates = [
            os.path.join(project_root, 'ingest', 'get_forecast_data.py'),
            os.path.join(os.path.dirname(project_root), 'ingest', 'get_forecast_data.py'),
            os.path.join(os.getcwd(), 'ingest', 'get_forecast_data.py'),
        ]
        
        self.forecast_script_path = None
        for candidate in forecast_candidates:
            if os.path.exists(candidate):
                self.forecast_script_path = candidate
                break
        
        if not self.forecast_script_path:
            self.forecast_script_path = forecast_candidates[0]  # Default fallback
        
        logger.info(f"Data ingestion scheduler initialized:")
        logger.info(f"  Station readings: interval={self.station_polling_interval_minutes}min, enabled={self.enable_station_scheduler}")
        logger.info(f"  Forecast data: interval={self.forecast_polling_interval_minutes}min, enabled={self.enable_forecast_scheduler}")
    
    def _job_listener(self, event):
        """
        Listen for job execution events and log results.
        
        Args:
            event: APScheduler job event
        """
        if event.exception:
            job_type = "station reading" if "station" in event.job_id else "forecast"
            logger.error(f"{job_type.capitalize()} job failed: {event.exception}")
        else:
            job_type = "station reading" if "station" in event.job_id else "forecast"
            logger.info(f"{job_type.capitalize()} job completed successfully at {datetime.now(timezone.utc)}")
    
    def _run_station_reading_script(self):
        """
        Execute the get_station_reading.py script in a subprocess.
        
        This method is called by the scheduler at each interval.
        """
        if self._shutdown_event.is_set():
            logger.info("Shutdown event set, skipping station reading job")
            return
        
        try:
            print("=== STATION READING JOB STARTING ===")
            start_time = datetime.now(timezone.utc)
            logger.info(f"Starting station reading ingestion at {start_time}")
            
            # Prepare command
            python_executable = sys.executable
            cmd = [python_executable, self.station_script_path, '--log-level', 'INFO']
            
            print(f"=== STATION: Executing command: {' '.join(cmd)} ===")
            
            # Execute script with timeout
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(self.station_script_path) if self.station_script_path else os.getcwd()
            )
            
            try:
                stdout, stderr = process.communicate(timeout=self.station_script_timeout_seconds)
                return_code = process.returncode
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                if return_code == 0:
                    print(f"=== STATION: Completed successfully in {duration:.1f}s ===")
                    logger.info(f"Station reading script completed successfully in {duration:.1f}s")
                    # Print stdout to main terminal to show station logs
                    if stdout.strip():
                        print(f"--- STATION READING OUTPUT ---")
                        print(stdout.strip())
                        print(f"--- END STATION OUTPUT ---")
                else:
                    print(f"=== STATION: Failed with code {return_code} after {duration:.1f}s ===")
                    logger.error(f"Station reading script failed with code {return_code} after {duration:.1f}s")
                    if stderr.strip():
                        print(f"--- STATION ERROR OUTPUT ---")
                        print(f"STDERR: {stderr.strip()}")
                        if stdout.strip():
                            print(f"STDOUT: {stdout.strip()}")
                        print(f"--- END STATION ERROR ---")
                        
            except subprocess.TimeoutExpired:
                print(f"=== STATION: Timed out after {self.station_script_timeout_seconds}s ===")
                logger.error(f"Station reading script timed out after {self.station_script_timeout_seconds}s")
                process.kill()
                process.communicate()  # Clean up
                raise
                
        except Exception as e:
            print(f"=== STATION: ERROR: {e} ===")
            logger.error(f"Error executing station reading script: {e}")
            raise
    
    def _run_forecast_ingestion_script(self):
        """
        Execute the get_forecast_data.py script in a subprocess.
        
        This method is called by the scheduler at each interval.
        """
        if self._shutdown_event.is_set():
            logger.info("Shutdown event set, skipping forecast ingestion job")
            return
        
        try:
            print("=== FORECAST INGESTION JOB STARTING ===")
            start_time = datetime.now(timezone.utc)
            logger.info(f"Starting forecast data ingestion at {start_time}")
            
            # Prepare command
            python_executable = sys.executable
            cmd = [python_executable, self.forecast_script_path, '--log-level', 'INFO']
            
            print(f"=== FORECAST: Executing command: {' '.join(cmd)} ===")
            
            # Execute script with timeout
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(self.forecast_script_path) if self.forecast_script_path else os.getcwd()
            )
            
            try:
                stdout, stderr = process.communicate(timeout=self.forecast_script_timeout_seconds)
                return_code = process.returncode
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                if return_code == 0:
                    print(f"=== FORECAST: Completed successfully in {duration:.1f}s ===")
                    logger.info(f"Forecast ingestion script completed successfully in {duration:.1f}s")
                    # Display forecast logs (they go to stderr, not stdout)
                    if stderr.strip():
                        print(f"--- FORECAST INGESTION OUTPUT ---")
                        print(stderr.strip())
                        print(f"--- END FORECAST OUTPUT ---")
                    elif stdout.strip():
                        print(f"--- FORECAST INGESTION OUTPUT ---")
                        print(stdout.strip())
                        print(f"--- END FORECAST OUTPUT ---")
                    else:
                        print("=== FORECAST: No output to display ===")
                else:
                    print(f"=== FORECAST: Failed with code {return_code} after {duration:.1f}s ===")
                    logger.error(f"Forecast ingestion script failed with code {return_code} after {duration:.1f}s")
                    if stderr.strip():
                        print(f"--- FORECAST ERROR OUTPUT ---")
                        print(f"STDERR: {stderr.strip()}")
                        if stdout.strip():
                            print(f"STDOUT: {stdout.strip()}")
                        print(f"--- END FORECAST ERROR ---")
                        
            except subprocess.TimeoutExpired:
                print(f"=== FORECAST: Timed out after {self.forecast_script_timeout_seconds}s ===")
                logger.error(f"Forecast ingestion script timed out after {self.forecast_script_timeout_seconds}s")
                process.kill()
                process.communicate()  # Clean up
                raise
                
        except Exception as e:
            print(f"=== FORECAST: ERROR: {e} ===")
            logger.error(f"Error executing forecast ingestion script: {e}")
            raise

    def start(self):
        """
        Start the background scheduler for both station readings and forecasts.
        
        Returns:
            bool: True if started successfully
        """
        if not (self.enable_station_scheduler or self.enable_forecast_scheduler):
            logger.info("Both station and forecast schedulers disabled by configuration")
            return True
            
        if self.is_running:
            logger.warning("Data ingestion scheduler already running")
            return True
        
        try:
            # Verify scripts exist
            if self.enable_station_scheduler and not os.path.exists(self.station_script_path):
                logger.error(f"Station reading script not found: {self.station_script_path}")
                return False
            
            if self.enable_forecast_scheduler and not os.path.exists(self.forecast_script_path):
                logger.error(f"Forecast ingestion script not found: {self.forecast_script_path}")
                return False
            
            # Create and configure scheduler
            self.scheduler = BackgroundScheduler(
                job_defaults={
                    'coalesce': True,  # Combine multiple pending executions into one
                    'max_instances': 1,  # Only one instance of each job at a time
                    'misfire_grace_time': 300  # 5 minutes grace for missed jobs
                }
            )
            
            # Add job listener for logging
            self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            
            # Add station reading job if enabled (recurring every hour)
            if self.enable_station_scheduler:
                self.scheduler.add_job(
                    func=self._run_station_reading_script,
                    trigger=IntervalTrigger(minutes=self.station_polling_interval_minutes),
                    id='station_reading_job',
                    name='Station Reading Ingestion',
                    replace_existing=True
                )
                logger.info(f"Station reading job scheduled with {self.station_polling_interval_minutes}-minute interval")
            
            # Add forecast ingestion job if enabled (recurring every 6 hours)
            if self.enable_forecast_scheduler:
                self.scheduler.add_job(
                    func=self._run_forecast_ingestion_script,
                    trigger=IntervalTrigger(minutes=self.forecast_polling_interval_minutes),
                    id='forecast_ingestion_job',
                    name='Forecast Data Ingestion',
                    replace_existing=True
                )
                logger.info(f"Forecast ingestion job scheduled with {self.forecast_polling_interval_minutes}-minute interval")

            # Add alerts monitor job if available and enabled
            try:
                alert_enabled = os.environ.get('ALERT_MONITOR_ENABLED', 'true').lower() in ['true', '1', 'on', 'yes']
                alert_interval = int(os.environ.get('ALERT_MONITOR_INTERVAL_MINUTES', '15'))
            except Exception:
                alert_enabled = True
                alert_interval = 15

            if alert_enabled and monitor_favorite_stations is not None:
                # Ensure the monitor runs inside the Flask application context
                def _alerts_job_wrapper():
                    try:
                        if self.app:
                            with self.app.app_context():
                                monitor_favorite_stations()
                        else:
                            monitor_favorite_stations()
                    except Exception:
                        logger.exception('Alerts monitor job failed')

                self.scheduler.add_job(
                    func=_alerts_job_wrapper,
                    trigger=IntervalTrigger(minutes=alert_interval),
                    id='alerts_monitor_job',
                    name='Alerts Monitor',
                    replace_existing=True
                )
                logger.info(f"Alerts monitor job scheduled with {alert_interval}-minute interval")
            
            # Start scheduler FIRST
            self.scheduler.start()
            self.is_running = True
            logger.info("Data ingestion scheduler started successfully")
            
            # IMMEDIATELY run initial jobs to show logs on startup - NO DELAYS
            print("=== SCHEDULER STARTUP: Running initial jobs immediately ===")
            
            if self.enable_station_scheduler:
                print("=== Running initial STATION READING job ===")
                # Run station reading immediately in background thread to avoid blocking
                import threading
                station_thread = threading.Thread(target=self._run_station_reading_script, name="InitialStationReading")
                station_thread.daemon = True
                station_thread.start()
            
            if self.enable_forecast_scheduler:
                print("=== Running initial FORECAST INGESTION job ===")
                # Run forecast immediately in background thread to avoid blocking  
                import threading
                forecast_thread = threading.Thread(target=self._run_forecast_ingestion_script, name="InitialForecastIngestion")
                forecast_thread.daemon = True
                forecast_thread.start()

            # Run alerts monitor immediately if enabled and available
            try:
                alert_enabled = os.environ.get('ALERT_MONITOR_ENABLED', 'true').lower() in ['true', '1', 'on', 'yes']
            except Exception:
                alert_enabled = True

            if alert_enabled and monitor_favorite_stations is not None:
                print("=== Running initial ALERTS MONITOR job ===")
                def _initial_alerts_target():
                    try:
                        if self.app:
                            with self.app.app_context():
                                monitor_favorite_stations()
                        else:
                            monitor_favorite_stations()
                    except Exception:
                        logger.exception('Initial alerts monitor failed')

                alert_thread = threading.Thread(target=_initial_alerts_target, name="InitialAlertsMonitor")
                alert_thread.daemon = True
                alert_thread.start()
            
            print("=== SCHEDULER STARTUP: Both initial jobs started ===")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start data ingestion scheduler: {e}")
            return False
    
    def stop(self, wait: bool = True):
        """
        Stop the background scheduler gracefully.
        
        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self.is_running:
            return
        
        logger.info("Stopping data ingestion scheduler...")
        self._shutdown_event.set()
        
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=wait)
                logger.info("Data ingestion scheduler stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping data ingestion scheduler: {e}")
        
        self.is_running = False
    
    def get_status(self) -> dict:
        """
        Get scheduler status and job information.
        
        Returns:
            dict: Status information
        """
        if not self.scheduler:
            return {
                'running': False,
                'station_scheduler': {
                    'enabled': self.enable_station_scheduler,
                    'interval_minutes': self.station_polling_interval_minutes
                },
                'forecast_scheduler': {
                    'enabled': self.enable_forecast_scheduler,
                    'interval_minutes': self.forecast_polling_interval_minutes
                }
            }
        
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                'id': job.id,
                'name': job.name,
                'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
                'trigger': str(job.trigger)
            })
        
        return {
            'running': self.is_running,
            'station_scheduler': {
                'enabled': self.enable_station_scheduler,
                'interval_minutes': self.station_polling_interval_minutes,
                'timeout_seconds': self.station_script_timeout_seconds
            },
            'forecast_scheduler': {
                'enabled': self.enable_forecast_scheduler,
                'interval_minutes': self.forecast_polling_interval_minutes,
                'timeout_seconds': self.forecast_script_timeout_seconds
            },
            'jobs': jobs
        }


# Global scheduler instance
_scheduler_instance: Optional[DataIngestionScheduler] = None


def init_scheduler(app):
    """
    Initialize and start the data ingestion scheduler with Flask app.
    
    Args:
        app: Flask application instance
    """
    global _scheduler_instance
    
    if _scheduler_instance is not None:
        logger.warning("Data ingestion scheduler already initialized")
        return _scheduler_instance
    
    try:
        _scheduler_instance = DataIngestionScheduler(app)
        
        # Start scheduler
        success = _scheduler_instance.start()
        
        if success:
            # Register proper shutdown for app exit only
            import atexit
            def shutdown_on_exit():
                if _scheduler_instance and _scheduler_instance.is_running:
                    logger.info("Shutting down data ingestion scheduler on app exit")
                    _scheduler_instance.stop(wait=False)
            
            atexit.register(shutdown_on_exit)
            
            logger.info("Data ingestion scheduler integrated with Flask app")
        else:
            logger.error("Failed to start data ingestion scheduler")
            
        return _scheduler_instance
        
    except Exception as e:
        logger.error(f"Failed to initialize data ingestion scheduler: {e}")
        return None


def get_scheduler() -> Optional[DataIngestionScheduler]:
    """
    Get the global scheduler instance.
    
    Returns:
        DataIngestionScheduler instance or None if not initialized
    """
    return _scheduler_instance


def start_scheduler_with_app(app):
    """
    Convenience function to start scheduler with Flask app.
    
    Args:
        app: Flask application instance
    """
    return init_scheduler(app)


# Backward compatibility aliases for existing references
StationReadingScheduler = DataIngestionScheduler