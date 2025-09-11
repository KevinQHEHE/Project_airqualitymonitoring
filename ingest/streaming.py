"""
Background scheduler for periodic station reading ingestion.

Purpose: Run get_station_reading.py script periodically via configurable schedule.
Uses APScheduler for robust job scheduling with proper shutdown handling.
Integrates with Flask app lifecycle for startup/teardown.

Key decisions:
- Uses BackgroundScheduler for non-blocking operation
- Subprocess execution for isolation from main Flask process
- Configurable interval via environment variable
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
from datetime import datetime, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

logger = logging.getLogger(__name__)

class StationReadingScheduler:
    """
    Background scheduler for periodic station reading ingestion.
    
    Features:
    - Configurable polling interval via environment variables
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
        
        # Configuration from environment
        self.polling_interval_minutes = int(os.environ.get('STATION_POLLING_INTERVAL_MINUTES', '60'))
        self.script_timeout_seconds = int(os.environ.get('STATION_SCRIPT_TIMEOUT_SECONDS', '300'))
        self.enable_scheduler = os.environ.get('ENABLE_STATION_SCHEDULER', 'true').lower() in ['true', '1', 'on', 'yes']
        
        # Script path
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # Handle case where we're running from different contexts
        script_candidates = [
            os.path.join(project_root, 'ingest', 'get_station_reading.py'),
            os.path.join(os.path.dirname(project_root), 'ingest', 'get_station_reading.py'),
            os.path.join(os.getcwd(), 'ingest', 'get_station_reading.py'),
        ]
        
        self.script_path = None
        for candidate in script_candidates:
            if os.path.exists(candidate):
                self.script_path = candidate
                break
        
        if not self.script_path:
            self.script_path = script_candidates[0]  # Default fallback
        
        logger.info(f"Station scheduler initialized: interval={self.polling_interval_minutes}min, enabled={self.enable_scheduler}")
    
    def _job_listener(self, event):
        """
        Listen for job execution events and log results.
        
        Args:
            event: APScheduler job event
        """
        if event.exception:
            logger.error(f"Station reading job failed: {event.exception}")
        else:
            logger.info(f"Station reading job completed successfully at {datetime.now(timezone.utc)}")
    
    def _run_station_reading_script(self):
        """
        Execute the get_station_reading.py script in a subprocess.
        
        This method is called by the scheduler at each interval.
        """
        if self._shutdown_event.is_set():
            logger.info("Shutdown event set, skipping station reading job")
            return
        
        try:
            start_time = datetime.now(timezone.utc)
            logger.info(f"Starting station reading ingestion at {start_time}")
            
            # Prepare command
            python_executable = sys.executable
            cmd = [python_executable, self.script_path, '--log-level', 'INFO']
            
            # Execute script with timeout
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.path.dirname(self.script_path) if self.script_path else os.getcwd()
            )
            
            try:
                stdout, stderr = process.communicate(timeout=self.script_timeout_seconds)
                return_code = process.returncode
                
                end_time = datetime.now(timezone.utc)
                duration = (end_time - start_time).total_seconds()
                
                if return_code == 0:
                    logger.info(f"Station reading script completed successfully in {duration:.1f}s")
                    if stdout.strip():
                        logger.debug(f"Script stdout: {stdout.strip()}")
                else:
                    logger.error(f"Station reading script failed with code {return_code} after {duration:.1f}s")
                    if stderr.strip():
                        logger.error(f"Script stderr: {stderr.strip()}")
                    if stdout.strip():
                        logger.error(f"Script stdout: {stdout.strip()}")
                        
            except subprocess.TimeoutExpired:
                logger.error(f"Station reading script timed out after {self.script_timeout_seconds}s")
                process.kill()
                process.communicate()  # Clean up
                raise
                
        except Exception as e:
            logger.error(f"Error executing station reading script: {e}")
            raise
    
    def start(self):
        """
        Start the background scheduler.
        
        Returns:
            bool: True if started successfully
        """
        if not self.enable_scheduler:
            logger.info("Station scheduler disabled by configuration")
            return True
            
        if self.is_running:
            logger.warning("Station scheduler already running")
            return True
        
        try:
            # Verify script exists
            if not os.path.exists(self.script_path):
                logger.error(f"Station reading script not found: {self.script_path}")
                return False
            
            # Create and configure scheduler
            self.scheduler = BackgroundScheduler(
                job_defaults={
                    'coalesce': True,  # Combine multiple pending executions into one
                    'max_instances': 1,  # Only one instance of the job at a time
                    'misfire_grace_time': 300  # 5 minutes grace for missed jobs
                }
            )
            
            # Add job listener for logging
            self.scheduler.add_listener(self._job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            
            # Add the periodic job
            self.scheduler.add_job(
                func=self._run_station_reading_script,
                trigger=IntervalTrigger(minutes=self.polling_interval_minutes),
                id='station_reading_job',
                name='Station Reading Ingestion',
                replace_existing=True
            )
            
            # Start scheduler
            self.scheduler.start()
            self.is_running = True
            
            logger.info(f"Station scheduler started with {self.polling_interval_minutes}-minute interval")
            
            # Run initial job after a short delay to allow app startup to complete
            self.scheduler.add_job(
                func=self._run_station_reading_script,
                trigger='date',
                run_date=datetime.now(timezone.utc).replace(second=0, microsecond=0),
                id='initial_station_reading_job',
                name='Initial Station Reading',
                replace_existing=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to start station scheduler: {e}")
            return False
    
    def stop(self, wait: bool = True):
        """
        Stop the background scheduler gracefully.
        
        Args:
            wait: Whether to wait for running jobs to complete
        """
        if not self.is_running:
            return
        
        logger.info("Stopping station scheduler...")
        self._shutdown_event.set()
        
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=wait)
                logger.info("Station scheduler stopped successfully")
            except Exception as e:
                logger.error(f"Error stopping station scheduler: {e}")
        
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
                'enabled': self.enable_scheduler,
                'interval_minutes': self.polling_interval_minutes
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
            'enabled': self.enable_scheduler,
            'interval_minutes': self.polling_interval_minutes,
            'timeout_seconds': self.script_timeout_seconds,
            'jobs': jobs
        }


# Global scheduler instance
_scheduler_instance: Optional[StationReadingScheduler] = None


def init_scheduler(app):
    """
    Initialize and start the station reading scheduler with Flask app.
    
    Args:
        app: Flask application instance
    """
    global _scheduler_instance
    
    if _scheduler_instance is not None:
        logger.warning("Station scheduler already initialized")
        return _scheduler_instance
    
    try:
        _scheduler_instance = StationReadingScheduler(app)
        
        # Start scheduler
        success = _scheduler_instance.start()
        
        if success:
            # Register shutdown handler
            @app.teardown_appcontext
            def shutdown_scheduler(exception):
                if _scheduler_instance:
                    _scheduler_instance.stop(wait=False)
            
            # Also register with atexit for non-Flask shutdowns
            atexit.register(lambda: _scheduler_instance.stop(wait=False) if _scheduler_instance else None)
            
            logger.info("Station scheduler integrated with Flask app")
        else:
            logger.error("Failed to start station scheduler")
            
        return _scheduler_instance
        
    except Exception as e:
        logger.error(f"Failed to initialize station scheduler: {e}")
        return None


def get_scheduler() -> Optional[StationReadingScheduler]:
    """
    Get the global scheduler instance.
    
    Returns:
        StationReadingScheduler instance or None if not initialized
    """
    return _scheduler_instance


def start_scheduler_with_app(app):
    """
    Convenience function to start scheduler with Flask app.
    
    Args:
        app: Flask application instance
    """
    return init_scheduler(app)
