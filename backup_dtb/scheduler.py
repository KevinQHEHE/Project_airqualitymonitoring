"""Periodic backup scheduler for MongoDB archives."""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from backup_dtb.backup_data import backup_database, load_config

DEFAULT_INTERVAL_HOURS = 24.0
DEFAULT_RETENTION_DAYS = 14

_MODULE_LOGGER = logging.getLogger("backup_scheduler")

_scheduler_lock = threading.Lock()
_scheduler: Optional["BackupScheduler"] = None


def _parse_float(value: Optional[str], default: float) -> float:
    try:
        if value is None:
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


class BackupScheduler:
    """Lightweight background scheduler for invoking database backups."""

    def __init__(
        self,
        backup_root: Path,
        interval_hours: float = DEFAULT_INTERVAL_HOURS,
        retention_days: float = DEFAULT_RETENTION_DAYS,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.backup_root = Path(backup_root)
        self.interval_seconds = max(1.0, float(interval_hours) * 3600.0)
        self.retention_days = max(0.0, float(retention_days))
        self.logger = logger or _MODULE_LOGGER

        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._job_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

        self._is_running = False
        self._last_run_started: Optional[datetime] = None
        self._last_run_finished: Optional[datetime] = None
        self._last_result: Optional[Dict[str, str]] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self) -> None:
        with self._state_lock:
            if self._is_running:
                self.logger.debug("Backup scheduler already running")
                return

            self.backup_root.mkdir(parents=True, exist_ok=True)
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="BackupSchedulerThread",
                daemon=True,
            )
            self._thread.start()
            self._is_running = True
            self.logger.info(
                "Backup scheduler started (interval=%.4fh, retention=%.4fd)",
                self.interval_seconds / 3600.0,
                self.retention_days,
            )

    def stop(self) -> None:
        with self._state_lock:
            if not self._is_running:
                return
            self.logger.info("Stopping backup scheduler")
            self._stop_event.set()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=min(self.interval_seconds, 5.0))
            self._thread = None
            self._is_running = False

    def trigger_backup(self, reason: str = "manual", run_async: bool = True) -> bool:
        """Trigger a backup run.

        Args:
            reason: Label for logging and status tracking.
            run_async: If True, execute in a new thread.

        Returns:
            bool: True if a backup was started, False if one is already running.
        """
        if not self._is_running and run_async:
            self.logger.debug(
                "Trigger requested while scheduler stopped; proceeding in ad-hoc mode"
            )

        acquired = self._job_lock.acquire(blocking=False)
        if not acquired:
            self.logger.info("Backup request skipped (another run is in progress)")
            return False

        def _job() -> None:
            try:
                self._execute_backup(reason)
            finally:
                self._job_lock.release()

        if run_async:
            threading.Thread(target=_job, name="BackupJobThread", daemon=True).start()
        else:
            try:
                _job()
            except Exception:
                # _job handles its own exceptions, but guard regardless
                self.logger.exception("Unexpected error in synchronous backup execution")

        return True

    def is_backup_in_progress(self) -> bool:
        return self._job_lock.locked()

    def get_status(self) -> Dict[str, object]:
        return {
            "is_running": self._is_running,
            "backup_in_progress": self.is_backup_in_progress(),
            "interval_hours": round(self.interval_seconds / 3600.0, 4),
            "retention_days": self.retention_days,
            "last_run_started_at": self._format_dt(self._last_run_started),
            "last_run_finished_at": self._format_dt(self._last_run_finished),
            "last_result": self._last_result or {},
            "backup_root": str(self.backup_root),
        }

    def _run_loop(self) -> None:
        # Wait zero seconds for the first loop iteration so backups run soon after startup.
        delay = 0.0
        while not self._stop_event.wait(delay):
            # Run backup synchronously within loop, so the interval counts from end of run.
            self.trigger_backup(reason="scheduled", run_async=False)
            delay = self.interval_seconds

    def _execute_backup(self, reason: str) -> None:
        start_time = datetime.utcnow()
        self._last_run_started = start_time
        self.logger.info("Backup run started (%s)", reason)

        cfg = load_config()
        mongo_uri = cfg.get("MONGO_URI")
        mongo_db = cfg.get("MONGO_DB")
        if not mongo_uri or not mongo_db:
            message = "Missing MONGO_URI or MONGO_DB; backup aborted"
            self.logger.error(message)
            self._last_run_finished = datetime.utcnow()
            self._last_result = {
                "status": "error",
                "reason": reason,
                "error": message,
            }
            return

        try:
            archive_path = backup_database(
                mongo_uri=mongo_uri,
                db_name=mongo_db,
                out_root=self.backup_root,
            )
            self.logger.info("Backup run completed (%s): %s", reason, archive_path)
            self._apply_retention()
            result = {
                "status": "ok",
                "reason": reason,
                "archive_path": str(archive_path),
            }
        except Exception as exc:  # noqa: BLE001 - surface full context for operators
            self.logger.exception("Backup run failed (%s)", reason)
            result = {
                "status": "error",
                "reason": reason,
                "error": str(exc),
            }

        self._last_result = result
        self._last_run_finished = datetime.utcnow()

    def _apply_retention(self) -> None:
        if self.retention_days <= 0:
            self.logger.debug("Retention disabled or non-positive; skipping cleanup")
            return

        archive_dir = self.backup_root / "backup_data"
        if not archive_dir.exists():
            self.logger.debug("Archive directory %s does not exist; skipping retention", archive_dir)
            return

        cutoff = datetime.utcnow() - timedelta(days=self.retention_days)
        for tar_file in sorted(archive_dir.glob("backup_*.tar")):
            try:
                modified = datetime.utcfromtimestamp(tar_file.stat().st_mtime)
            except OSError as exc:  # noqa: PERF203 inert for readability
                self.logger.warning("Could not read metadata for %s: %s", tar_file, exc)
                continue

            if modified < cutoff:
                try:
                    tar_file.unlink()
                    self.logger.info("Removed expired backup archive: %s", tar_file)
                except Exception as exc:  # noqa: BLE001
                    self.logger.exception("Failed to remove archive %s: %s", tar_file, exc)

    @staticmethod
    def _format_dt(value: Optional[datetime]) -> Optional[str]:
        if not value:
            return None
        return value.replace(microsecond=0).isoformat() + "Z"


def init_backup_scheduler(logger: Optional[logging.Logger] = None) -> BackupScheduler:
    """Create (or return existing) scheduler instance and ensure it is started."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.is_running:
            return _scheduler

        load_dotenv()

        interval_env = os.getenv("BACKUP_INTERVAL_HOURS")
        retention_env = os.getenv("RETENTION_DAYS")

        interval_hours = _parse_float(interval_env, DEFAULT_INTERVAL_HOURS)
        retention_days = max(0.0, _parse_float(retention_env, DEFAULT_RETENTION_DAYS))

        backup_root = Path(__file__).resolve().parent
        scheduler = BackupScheduler(
            backup_root=backup_root,
            interval_hours=interval_hours,
            retention_days=retention_days,
            logger=logger,
        )
        scheduler.start()
        _scheduler = scheduler
        return scheduler


def get_backup_scheduler() -> Optional[BackupScheduler]:
    """Return the global backup scheduler instance if initialized."""
    with _scheduler_lock:
        return _scheduler
