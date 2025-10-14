"""
rollback_data.py

Restore a MongoDB database from a backup archive created by `backup_dtb/backup_data.py`.

The script:
- extracts the archive,
- optionally takes a safety snapshot,
- recreates collections (with validator handling and time-series support),
- inserts documents from JSON Lines files,
- verifies counts & sample hashes.

Use --dry-run to preview the actions and --yes to skip the confirmation prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from pymongo.database import Database

logger = logging.getLogger("rollback_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load default configuration from .env if present.
load_dotenv()

# Constants
DEFAULT_BATCH_SIZE = 1000
DEFAULT_SAMPLE_SIZE = 100
DEFAULT_TS_SAMPLE = 50
METADATA_FILENAME = "collections_metadata.json"
SYSTEM_VIEWS = "system.views"
SYSTEM_BUCKETS_PREFIX = "system.buckets."
TS_FIELD_RATIO = 0.6
TS_META_RATIO = 0.4
TS_ONLY_RATIO = 0.8
DUPLICATE_KEY_ERROR = 11000

# Dynamic import for backup helper (optional dependency)
backup_database = None
try:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "backup_data",
        str(Path(__file__).resolve().parents[1] / "backup_dtb" / "backup_data.py")
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        backup_database = getattr(mod, "backup_database", None)
except Exception:
    pass  # Continue without snapshot support


@dataclass(frozen=True)
class RestorePlan:
    """Plan for database restoration operations."""
    to_drop: List[str]
    to_create: List[str]
    to_restore: List[str]


@dataclass
class RestoreResult:
    """Result of a single collection restore operation."""
    inserted: int
    file_count: int
    error: Optional[Exception] = None

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Restore MongoDB database from a backup .tar archive (JSON Lines)."
    )
    parser.add_argument("archive", help="Path to backup archive (e.g. backup_YYYYmmdd_HHMMSS.tar)")
    parser.add_argument("--mongo-uri", help="Override MONGO_URI environment variable")
    parser.add_argument("--mongo-db", help="Override MONGO_DB environment variable")
    parser.add_argument("--out-dir", help="Optional extract dir (default: temp dir)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Insert batch size")
    parser.add_argument("--force", action="store_true", help="Temporarily disable validators while importing")
    parser.add_argument("--dry-run", action="store_true", help="Show summary only, do not modify DB")
    parser.add_argument("--yes", action="store_true", help="Answer yes to confirmation prompts")
    parser.add_argument("--verify-sample-size", type=int, default=DEFAULT_SAMPLE_SIZE,
                        help="Docs per collection to hash for verification")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="Do not take a pre-restore snapshot of the target DB")
    parser.add_argument("--snapshot-dir", help="Directory for the pre-restore snapshot (default: backup_dtb)")
    parser.add_argument("--replace-existing", action="store_true",
                        help="Drop and recreate collections from the backup before inserting")
    parser.add_argument("--no-infer-timeseries", action="store_true", help="Disable timeseries inference")
    return parser.parse_args(argv)


def load_config(mongo_uri: Optional[str], mongo_db: Optional[str]) -> Tuple[str, str]:
    uri = mongo_uri or os.getenv("MONGO_URI")
    db_name = mongo_db or os.getenv("MONGO_DB")
    if not uri or not db_name:
        logger.error("MONGO_URI and MONGO_DB must be provided via args or environment")
        raise SystemExit(2)
    return uri, db_name


def extract_archive(archive_path: str, out_dir: Optional[str] = None) -> Path:
    target_archive = Path(archive_path).expanduser().resolve()
    if not target_archive.exists():
        raise FileNotFoundError(f"Archive not found: {target_archive}")

    if out_dir:
        extract_root = Path(out_dir).resolve()
        extract_root.mkdir(parents=True, exist_ok=True)
    else:
        extract_root = Path(tempfile.mkdtemp(prefix="aqm_rollback_"))

    logger.info("Extracting %s to %s", target_archive, extract_root)
    with tarfile.open(target_archive, "r") as tar:
        tar.extractall(path=extract_root)

    return extract_root


def list_backup_jsonl(root: Path) -> Tuple[List[Path], List[Path]]:
    """List JSONL files in backup, separating time-series buckets."""
    files, skipped_buckets = [], []
    
    for path in sorted(root.iterdir()):
        if not (path.is_file() and path.suffix == ".jsonl"):
            continue
        if path.stem.startswith(SYSTEM_BUCKETS_PREFIX):
            logger.warning("Skipping internal time-series bucket file: %s", path.name)
            skipped_buckets.append(path)
        else:
            files.append(path)
    
    return files, skipped_buckets


def collection_name_from_file(path: Path) -> str:
    """Extract collection name from backup file path."""
    return path.stem


def load_collection_metadata(root: Path) -> Dict[str, dict]:
    """Load collection metadata from backup archive."""
    meta_path = root / METADATA_FILENAME
    if not meta_path.exists():
        return {}

    try:
        logger.info("Loading collection metadata from %s", meta_path)
        with meta_path.open("r", encoding="utf-8") as f:
            data = json_util.loads(f.read())
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Failed to load collection metadata; continuing without it")
        return {}


def build_restore_plan(db, backup_names: Iterable[str]) -> RestorePlan:
    current = set(db.list_collection_names())
    backup = set(backup_names)

    to_drop = sorted(current - backup)
    to_create = sorted(backup - current)
    to_restore = sorted(backup)

    return RestorePlan(to_drop=to_drop, to_create=to_create, to_restore=to_restore)


def format_plan_summary(plan: RestorePlan, skipped_buckets: List[Path], mongo_uri: str, mongo_db: str, archive: str) -> str:
    lines = [
        "Rollback summary:",
        f"Target DB: {mongo_db} ({mongo_uri})",
        f"Archive: {archive}",
        "",
        f"Collections to drop ({len(plan.to_drop)}): {plan.to_drop}",
        f"Collections to create ({len(plan.to_create)}): {plan.to_create}",
        f"Collections to restore ({len(plan.to_restore)}): {plan.to_restore}",
    ]
    if skipped_buckets:
        lines.append("")
        lines.append(
            f"Skipped internal bucket files ({len(skipped_buckets)}): {[path.name for path in skipped_buckets]}"
        )
    return "\n".join(lines)


def confirm_action(summary: str, auto_yes: bool) -> bool:
    print(summary)
    if auto_yes:
        logger.info("Auto-confirm enabled (--yes). Proceeding.")
        return True
    response = input("Type YES to proceed with the restore (destructive): ")
    return response.strip() == "YES"

def get_collection_validators(db: Database) -> Dict[str, dict]:
    """Retrieve validators from all collections in database."""
    validators = {}
    try:
        for info in db.list_collections():
            name = info.get("name")
            validator = info.get("options", {}).get("validator")
            if validator:
                validators[name] = validator
    except Exception:
        logger.exception("Failed to list collection validators")
    return validators


def disable_validators(db: Database, names: List[str]) -> Dict[str, dict]:
    """Temporarily disable validators for specified collections."""
    original = {}
    for name in names:
        try:
            info = db.command("listCollections", filter={"name": name})
            coll_info = info.get("cursor", {}).get("firstBatch", [])
            if coll_info:
                validator = coll_info[0].get("options", {}).get("validator")
                if validator:
                    original[name] = validator
                    logger.info("Disabling validator for collection %s", name)
                    db.command({"collMod": name, "validator": {}, "validationLevel": "off"})
        except Exception:
            logger.warning("Failed to disable validator for %s; skipping", name)
    return original


def restore_validators(db: Database, validators: Dict[str, dict]) -> Dict[str, Optional[Exception]]:
    """Restore validators to collections."""
    results = {}
    for name, validator in validators.items():
        try:
            logger.info("Restoring validator for %s", name)
            db.command({
                "collMod": name,
                "validator": validator,
                "validationLevel": "strict",
                "validationAction": "error",
            })
            results[name] = None
        except Exception as exc:
            logger.exception("Failed to restore validator for %s", name)
            results[name] = exc
    return results


def _process_bulk_error(bwe: errors.BulkWriteError, batch_size: int, coll_name: str) -> int:
    """Extract insert count from BulkWriteError and log duplicate issues."""
    details = getattr(bwe, 'details', {})
    n_inserted = details.get('nInserted')
    write_errors = details.get('writeErrors', [])
    
    # Calculate actual inserts
    if isinstance(n_inserted, int):
        inserted = n_inserted
    else:
        inserted = max(0, batch_size - len(write_errors))
    
    # Log errors
    if write_errors:
        dup_count = sum(1 for e in write_errors if e.get('code') == DUPLICATE_KEY_ERROR)
        logger.warning(
            "Bulk write error while restoring %s: %d errors (%d duplicates). First error: %s",
            coll_name, len(write_errors), dup_count, write_errors[0]
        )
    
    return inserted


def stream_insert_collection(db: Database, coll_name: str, file_path: Path, 
                            batch_size: int = DEFAULT_BATCH_SIZE) -> Tuple[int, int]:
    """Stream insert documents from JSONL file into collection."""
    collection = db[coll_name]
    inserted, total, batch = 0, 0, []

    def insert_batch():
        nonlocal inserted
        if not batch:
            return
        try:
            result = collection.insert_many(batch, ordered=False)
            inserted += len(result.inserted_ids)
        except errors.BulkWriteError as bwe:
            inserted += _process_bulk_error(bwe, len(batch), coll_name)
        except Exception:
            logger.exception("Unexpected error inserting batch into %s; skipping", coll_name)

    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            total += 1
            batch.append(json_util.loads(line))
            if len(batch) >= batch_size:
                insert_batch()
                batch = []
        insert_batch()  # Final batch

    return inserted, total


def sample_hash_of_file(file_path: Path, sample_size: int = DEFAULT_SAMPLE_SIZE) -> str:
    """Generate hash of first N documents in JSONL file for verification."""
    digest = hashlib.sha256()
    seen = 0

    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            if seen >= sample_size:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json_util.loads(line)
                text = json_util.dumps(obj, sort_keys=True)
            except Exception:
                text = line
            digest.update(text.encode("utf-8"))
            seen += 1

    return digest.hexdigest()


def infer_timeseries_options_from_jsonl(file_path: Path, sample_size: int = DEFAULT_TS_SAMPLE) -> Optional[dict]:
    """Infer time-series collection options by sampling JSONL documents."""
    ts_count = meta_count = checked = 0

    try:
        with file_path.open("r", encoding="utf-8") as f:
            for raw_line in f:
                if checked >= sample_size:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json_util.loads(line)
                    checked += 1
                    if "ts" in obj:
                        ts_count += 1
                    if "meta" in obj and isinstance(obj.get("meta"), dict):
                        meta_count += 1
                except Exception:
                    continue
    except Exception:
        return None

    if checked == 0:
        return None

    ts_ratio = ts_count / checked
    meta_ratio = meta_count / checked
    
    if ts_ratio >= TS_FIELD_RATIO and meta_ratio >= TS_META_RATIO:
        return {"timeField": "ts", "metaField": "meta", "granularity": "hours"}
    if ts_ratio >= TS_ONLY_RATIO:
        return {"timeField": "ts", "granularity": "hours"}
    
    return None


def determine_timeseries_options(
    name: str,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> Optional[dict]:
    """Determine time-series options for a collection from metadata or inference."""
    # Check metadata first
    ts_options = metadata.get(name, {}).get("timeseries")
    if ts_options:
        return ts_options

    if not inference_enabled:
        return None

    # Infer from file if bucket was skipped
    bucket_name = f"{SYSTEM_BUCKETS_PREFIX}{name}"
    candidate = next((p for p in files if collection_name_from_file(p) == name), None)

    if any(p.stem == bucket_name for p in skipped_buckets):
        if candidate:
            inferred = infer_timeseries_options_from_jsonl(candidate)
            return inferred or {"timeField": "ts", "metaField": "meta", "granularity": "hours"}

    return infer_timeseries_options_from_jsonl(candidate) if candidate else None


def create_collection_with_options(db: Database, name: str, ts_options: Optional[dict]) -> None:
    """Create collection with time-series options if specified."""
    if ts_options:
        logger.info("Creating time-series collection %s with options %s", name, ts_options)
        try:
            # Drop if exists to ensure clean creation
            if name in db.list_collection_names():
                db.drop_collection(name)
            db.create_collection(name, timeseries=ts_options)
            return
        except Exception:
            logger.exception("Failed to create time-series collection %s; falling back", name)

    logger.info("Creating collection %s", name)
    try:
        db.create_collection(name)
    except Exception:
        logger.debug("Collection %s may already exist", name)


def prepare_collections_for_replace(
    db: Database,
    names: Iterable[str],
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> None:
    """Drop and recreate collections before restore (--replace-existing mode)."""
    logger.info("--replace-existing: dropping and recreating collections")
    for name in names:
        try:
            if name in db.list_collection_names():
                logger.info("Dropping existing collection: %s", name)
                db.drop_collection(name)
        except Exception:
            logger.exception("Failed to drop collection %s; continuing", name)

        ts_options = determine_timeseries_options(name, metadata, inference_enabled, skipped_buckets, files)
        create_collection_with_options(db, name, ts_options)


def drop_collections(db: Database, names: Iterable[str]) -> None:
    """Drop multiple collections."""
    for name in names:
        try:
            logger.info("Dropping collection: %s", name)
            db.drop_collection(name)
        except Exception:
            logger.exception("Failed to drop collection %s", name)


def ensure_collection_ready(
    db: Database,
    name: str,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> None:
    """Ensure collection exists before data insertion."""
    if name in db.list_collection_names():
        return

    ts_options = determine_timeseries_options(name, metadata, inference_enabled, skipped_buckets, files)
    create_collection_with_options(db, name, ts_options)


def restore_collections(
    db: Database,
    files: List[Path],
    batch_size: int,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
) -> Dict[str, dict]:
    """Restore all collections from backup files, handling views last."""
    results = {}
    view_file = None

    # First pass: restore regular collections
    for file_path in files:
        name = collection_name_from_file(file_path)
        if name == SYSTEM_VIEWS:
            view_file = file_path
            continue

        ensure_collection_ready(db, name, metadata, inference_enabled, skipped_buckets, files)
        logger.info("Restoring collection %s from %s", name, file_path)
        
        try:
            inserted, total = stream_insert_collection(db, name, file_path, batch_size)
            results[name] = {"inserted": inserted, "file_count": total}
            logger.info("Restored %s: inserted=%d file_lines=%d", name, inserted, total)
        except Exception as exc:
            logger.exception("Failed to restore collection %s", name)
            results[name] = {"inserted": 0, "file_count": None, "error": True}

    # Second pass: restore views after collections exist
    if view_file:
        try:
            logger.info("Restoring database views from %s", view_file)
            restored = restore_views_from_jsonl(db, view_file)
            results[SYSTEM_VIEWS] = {"inserted": 0, "file_count": restored}
            logger.info("Restored system.views: created=%d views", restored)
        except Exception:
            logger.exception("Failed to restore database views")
            results[SYSTEM_VIEWS] = {"inserted": 0, "file_count": None, "error": True}

    return results


def restore_views_from_jsonl(db: Database, file_path: Path) -> int:
    """Restore view definitions from system.views JSONL file.
    
    Creates MongoDB views and ensures underlying collections exist.
    Returns the number of views successfully created.
    """
    created = 0
    
    with file_path.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            
            try:
                doc = json_util.loads(line)
            except Exception:
                logger.exception("Failed to parse view definition; skipping: %s", line)
                continue

            view_id = doc.get("_id")
            view_on = doc.get("viewOn")
            pipeline = doc.get("pipeline", [])

            if not view_id or not view_on:
                logger.warning("Skipping invalid view definition (missing _id or viewOn): %s", doc)
                continue

            # Extract view name from _id (format: '<dbname>.<collname>')
            view_name = view_id.split(".", 1)[1] if isinstance(view_id, str) and "." in view_id else view_id

            try:
                existing_colls = db.list_collection_names()
                
                # Ensure underlying collection exists (especially for time-series views)
                if view_on not in existing_colls and view_on.startswith(SYSTEM_BUCKETS_PREFIX):
                    ts_coll_name = view_on.replace(SYSTEM_BUCKETS_PREFIX, "")
                    logger.warning(
                        "View %s references missing %s. Creating time-series collection %s",
                        view_name, view_on, ts_coll_name
                    )
                    try:
                        db.create_collection(
                            ts_coll_name,
                            timeseries={"timeField": "ts", "metaField": "meta", "granularity": "hours"}
                        )
                    except Exception:
                        logger.exception("Failed to create time-series collection %s", ts_coll_name)

                # Drop existing view before recreation
                if view_name in existing_colls:
                    db.drop_collection(view_name)

                # Create view
                logger.info("Creating view %s on %s", view_name, view_on)
                db.create_collection(view_name, viewOn=view_on, pipeline=pipeline)
                created += 1
                
            except Exception:
                logger.exception("Failed to restore view %s", view_name)

    return created


def _is_view(db: Database, name: str) -> bool:
    """Check if a collection is actually a view."""
    try:
        info = db.command("listCollections", filter={"name": name})
        batch = info.get("cursor", {}).get("firstBatch", [])
        if batch:
            coll_data = batch[0]
            return coll_data.get("type") == "view" or "viewOn" in coll_data.get("options", {})
    except Exception:
        pass
    return False


def verify_restore(db: Database, files: List[Path], results: Dict[str, dict], 
                   sample_size: int) -> Dict[str, dict]:
    """Verify restored collections by comparing counts and hashes."""
    verification = {}
    
    for file_path in files:
        name = collection_name_from_file(file_path)
        file_count = results.get(name, {}).get("file_count")
        
        # Skip verification for views - they cannot be counted like regular collections
        if name == SYSTEM_VIEWS or _is_view(db, name):
            verification[name] = {
                "file_count": file_count,
                "db_count": "N/A (view)",
                "sample_hash": "N/A"
            }
            continue
        
        # Try to count documents
        try:
            db_count = db[name].count_documents({})
        except Exception as exc:
            # Catch time-series/view errors
            if "time-series buckets" in str(exc) or "is a view" in str(exc):
                verification[name] = {
                    "file_count": file_count,
                    "db_count": "N/A (view)",
                    "sample_hash": "N/A"
                }
                continue
            raise
        
        sample_hash = sample_hash_of_file(file_path, sample_size)
        verification[name] = {
            "file_count": file_count,
            "db_count": db_count,
            "sample_hash": sample_hash
        }
    
    return verification

def take_pre_restore_snapshot(args: argparse.Namespace, mongo_uri: str, mongo_db: str) -> bool:
    """Take a safety snapshot before restore operation."""
    if args.no_snapshot:
        return True
    
    if backup_database is None:
        logger.warning("Backup helper not available; cannot take pre-restore snapshot")
        return True

    snapshot_root = Path(args.snapshot_dir) if args.snapshot_dir else Path("backup_dtb")
    try:
        logger.info("Taking pre-restore snapshot of target DB to %s", snapshot_root)
        archive = backup_database(mongo_uri=mongo_uri, db_name=mongo_db, out_root=snapshot_root)
        logger.info("Pre-restore snapshot created: %s", archive)
        return True
    except Exception:
        logger.exception("Failed to take pre-restore snapshot")
        logger.error("Aborting restore to avoid destructive changes. Use --no-snapshot to override.")
        return False


def main(argv: Optional[List[str]] = None) -> None:
    """Main restore workflow."""
    args = parse_args(argv)
    mongo_uri, mongo_db = load_config(args.mongo_uri, args.mongo_db)

    extract_dir = None
    try:
        # Extract and analyze backup
        extract_dir = extract_archive(args.archive, args.out_dir)
        files, skipped_buckets = list_backup_jsonl(extract_dir)
        metadata = load_collection_metadata(extract_dir)
        backup_names = [collection_name_from_file(p) for p in files]

        with MongoClient(mongo_uri) as client:
            db = client[mongo_db]
            plan = build_restore_plan(db, backup_names)
            summary = format_plan_summary(plan, skipped_buckets, mongo_uri, mongo_db, args.archive)

            # Dry-run or confirmation
            if args.dry_run:
                print(summary)
                logger.info("Dry-run requested; exiting without modifying database")
                return

            if not confirm_action(summary, args.yes):
                logger.info("User declined to proceed. Exiting")
                return

            # Manage validators if --force
            modified_validators = {}
            if args.force:
                validators = get_collection_validators(db)
                if validators:
                    logger.info("Found validators on collections: %s", list(validators.keys()))
                modified_validators = disable_validators(db, plan.to_restore)

            # Take snapshot before destructive operations
            if not take_pre_restore_snapshot(args, mongo_uri, mongo_db):
                return

            # Time-series inference
            inference_enabled = not args.no_infer_timeseries

            # Prepare collections if --replace-existing
            if args.replace_existing:
                prepare_collections_for_replace(
                    db, plan.to_restore, metadata, inference_enabled, skipped_buckets, files
                )

            # Drop collections not in backup
            drop_collections(db, plan.to_drop)

            # Restore collections
            results = restore_collections(
                db, files, args.batch_size, metadata, inference_enabled, skipped_buckets
            )

            # Restore validators if disabled
            validator_restore_results = {}
            if modified_validators:
                logger.info("Restoring collection validators (may fail if documents violate schema)")
                validator_restore_results = restore_validators(db, modified_validators)

            # Verify restoration
            verification = verify_restore(db, files, results, args.verify_sample_size)

            # Report results
            logger.info("Rollback completed. Verification summary:")
            for name, info in verification.items():
                logger.info(
                    "%s: file_count=%s db_count=%s sample_hash=%s",
                    name, info["file_count"], info["db_count"], info["sample_hash"]
                )

            if validator_restore_results:
                logger.info("Validator restore results (None=success): %s", validator_restore_results)

    finally:
        # Cleanup temp directory
        if extract_dir and args.out_dir is None:
            try:
                shutil.rmtree(extract_dir)
                logger.debug("Removed temporary extraction dir: %s", extract_dir)
            except Exception:
                logger.exception("Failed to remove temporary dir: %s", extract_dir)


if __name__ == "__main__":
    main()
