"""
rollback_data.py

Restore a MongoDB database from a backup archive created by `backup_dtb/backup_data.py`.

Features:
- Extracts a `.tar` archive produced by the backup flow.
- Drops collections that are present in the target DB but not in the backup.
- Restores each collection from `.jsonl` files using `bson.json_util.loads` to preserve BSON types.
- Optionally temporarily disables collection validators during import (`--force`) and attempts to reapply them after import while logging any validation errors.
- Provides a dry-run summary and requires confirmation before destructive actions unless `--yes` is passed.

Safety: the script refuses to run without explicit confirmation for production-like databases unless `--yes` is used. Always test on staging first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient, errors
# (dynamic import will be attempted after logger is configured)

logger = logging.getLogger("rollback_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load .env file if present so environment defaults (MONGO_URI, MONGO_DB) are available
load_dotenv()

# Try to dynamically load the backup helper so we can create a pre-restore snapshot.
# This avoids requiring `backup_dtb` to be an importable package.
backup_database = None
try:
    import importlib.util
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / "backup_dtb" / "backup_data.py"
    if candidate.exists():
        spec = importlib.util.spec_from_file_location("backup_data", str(candidate))
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            backup_database = getattr(mod, "backup_database", None)
except Exception:
    logger.debug("Could not dynamically load backup helper; continuing without snapshot support")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Restore MongoDB database from a backup .tar archive (JSON Lines)."
    )
    p.add_argument("archive", help="Path to backup archive (e.g. backup_data/backup_YYYYmmdd_HHMMSS.tar)")
    p.add_argument("--mongo-uri", default=None, help="Override MONGO_URI environment variable")
    p.add_argument("--mongo-db", default=None, help="Override MONGO_DB environment variable")
    p.add_argument("--out-dir", default=None, help="Optional extract dir (default: temp dir)")
    p.add_argument("--batch-size", type=int, default=1000, help="Insert batch size")
    p.add_argument("--force", action="store_true", help="Temporarily disable validators while importing (DANGEROUS)")
    p.add_argument("--dry-run", action="store_true", help="Show summary only, do not modify DB")
    p.add_argument("--yes", action="store_true", help="Answer yes to confirmation prompts")
    p.add_argument("--verify-sample-size", type=int, default=100, help="Number of docs per collection to sample-hash for verification")
    p.add_argument("--no-snapshot", action="store_true", help="Do not take a pre-restore snapshot of the target DB")
    p.add_argument("--snapshot-dir", default=None, help="Directory to place the pre-restore snapshot (default: backup_dtb/rollback_snapshots)")
    p.add_argument("--replace-existing", action="store_true", help="Drop and recreate collections from the backup (ensures exact snapshot).")
    p.add_argument("--infer-timeseries", action="store_true", help="(deprecated) attempt to infer time-series options - kept for backward compatibility")
    p.add_argument("--no-infer-timeseries", action="store_true", help="Do not attempt to infer time-series options from data or bucket files (opt-out). By default inference is enabled.")
    return p.parse_args(argv)


def load_config(mongo_uri: Optional[str], mongo_db: Optional[str]) -> Tuple[str, str]:
    # read from environment if not provided
    uri = mongo_uri or os.getenv("MONGO_URI")
    db = mongo_db or os.getenv("MONGO_DB")
    if not uri or not db:
        logger.error("MONGO_URI and MONGO_DB must be provided via args or environment")
        raise SystemExit(2)
    return uri, db


def extract_archive(archive_path: str, out_dir: Optional[str] = None) -> Path:
    p_archive = Path(archive_path).expanduser().resolve()
    if not p_archive.exists():
        raise FileNotFoundError(f"Archive not found: {p_archive}")

    if out_dir:
        target = Path(out_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
    else:
        target = Path(tempfile.mkdtemp(prefix="aqm_rollback_"))

    logger.info("Extracting %s to %s", p_archive, target)
    with tarfile.open(p_archive, "r") as tar:
        tar.extractall(path=target)

    return target


def read_jsonl_path(root: Path) -> List[Path]:
    files = [p for p in sorted(root.iterdir()) if p.suffix == ".jsonl" and p.is_file()]
    return files


def collection_name_from_file(p: Path) -> str:
    # Reverse of sanitize_filename (best-effort): currently sanitize replaces os.sep and spaces with '_'
    # We assume original collection names did not contain path separators; return stem.
    return p.stem


def get_collection_validators(db) -> Dict[str, dict]:
    """Return a mapping collection_name -> options dict (including 'validator' if present)."""
    validators: Dict[str, dict] = {}
    try:
        for info in db.list_collections():
            name = info.get("name")
            options = info.get("options", {}) or {}
            if "validator" in options:
                validators[name] = options["validator"]
    except Exception:
        # Best-effort: some users may run on older drivers/permissions
        logger.exception("Failed to list collection validators; proceeding without validator info")
    return validators


def confirm_action(summary: str, auto_yes: bool) -> bool:
    print(summary)
    if auto_yes:
        logger.info("Auto-confirm enabled (--yes). Proceeding.")
        return True
    resp = input("Type YES to proceed with the restore (destructive): ")
    return resp.strip() == "YES"


def disable_validators(db, names: List[str]) -> Dict[str, dict]:
    """Temporarily remove validators for listed collections. Returns original validators mapping."""
    orig: Dict[str, dict] = {}
    for name in names:
        try:
            info = db.command("listCollections", filter={"name": name})
            coll_info = info.get("cursor", {}).get("firstBatch", [])
            if coll_info:
                opts = coll_info[0].get("options", {}) or {}
                if "validator" in opts:
                    orig[name] = opts["validator"]
                    # remove validator
                    logger.info("Disabling validator for collection %s", name)
                    db.command({"collMod": name, "validator": {}, "validationLevel": "off"})
        except errors.OperationFailure:
            logger.exception("Failed to disable validator for %s; skipping", name)
        except Exception:
            logger.exception("Unexpected error disabling validator for %s; skipping", name)
    return orig


def restore_validators(db, validators: Dict[str, dict]) -> Dict[str, Optional[Exception]]:
    """Attempt to reapply validators. Returns dict of name->exception (None if succeeded)."""
    results: Dict[str, Optional[Exception]] = {}
    for name, validator in validators.items():
        try:
            logger.info("Restoring validator for %s", name)
            db.command({"collMod": name, "validator": validator, "validationLevel": "strict", "validationAction": "error"})
            results[name] = None
        except Exception as e:
            logger.exception("Failed to restore validator for %s: %s", name, e)
            results[name] = e
    return results


def stream_insert_collection(db, coll_name: str, file_path: Path, batch_size: int = 1000) -> Tuple[int, int]:
    """Insert documents from a .jsonl file into collection. Returns (inserted_count, file_count)."""
    collection = db[coll_name]
    inserted = 0
    total = 0
    batch: List[dict] = []
    with file_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            total += 1
            doc = json_util.loads(line)
            batch.append(doc)
            if len(batch) >= batch_size:
                res = collection.insert_many(batch)
                inserted += len(res.inserted_ids)
                batch = []
        if batch:
            res = collection.insert_many(batch)
            inserted += len(res.inserted_ids)

    return inserted, total


def sample_hash_of_file(file_path: Path, sample_size: int = 100) -> str:
    h = hashlib.sha256()
    cnt = 0
    with file_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if cnt >= sample_size:
                break
            line = line.strip()
            if not line:
                continue
            # Normalize using bson.json_util.dumps to get deterministic-ish representation
            try:
                obj = json_util.loads(line)
                txt = json_util.dumps(obj, sort_keys=True)
            except Exception:
                txt = line
            h.update(txt.encode("utf-8"))
            cnt += 1
    return h.hexdigest()


def infer_timeseries_options_from_jsonl(file_path: Path, sample_size: int = 50) -> Optional[dict]:
    """Best-effort: examine up to `sample_size` lines and try to infer timeseries options.

    Heuristic:
    - If many docs contain a top-level 'ts' field with an ISO/datetime-like value, treat timeField='ts'.
    - If many docs contain a top-level 'meta' field that's a dict, treat metaField='meta'.
    - Set granularity='hours' as a sensible default when both present.

    Returns a dict suitable for db.create_collection(..., timeseries=opts) or None if inference failed.
    """
    ts_count = 0
    meta_count = 0
    checked = 0
    try:
        with file_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                if checked >= sample_size:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json_util.loads(line)
                except Exception:
                    continue
                checked += 1
                if 'ts' in obj:
                    ts_count += 1
                if 'meta' in obj and isinstance(obj.get('meta'), dict):
                    meta_count += 1
    except Exception:
        return None

    if checked == 0:
        return None

    # require a reasonable fraction to be present to avoid false positives
    ts_ratio = ts_count / checked
    meta_ratio = meta_count / checked
    if ts_ratio >= 0.6 and meta_ratio >= 0.4:
        return {"timeField": "ts", "metaField": "meta", "granularity": "hours"}
    if ts_ratio >= 0.8 and meta_ratio < 0.4:
        return {"timeField": "ts", "granularity": "hours"}
    return None


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    mongo_uri, mongo_db = load_config(args.mongo_uri, args.mongo_db)

    extract_dir = None
    try:
        extract_dir = extract_archive(args.archive, args.out_dir)
        files_all = read_jsonl_path(extract_dir)
        # Skip internal time-series bucket collections (system.buckets.<name>) because
        # those are managed by MongoDB when creating a time-series collection. Restoring
        # the corresponding logical collection (e.g. 'waqi_station_readings') is sufficient.
        skipped_buckets: List[Path] = []
        files = []
        for p in files_all:
            if p.stem.startswith("system.buckets."):
                logger.warning("Skipping internal time-series bucket file: %s", p.name)
                skipped_buckets.append(p)
            else:
                files.append(p)

        backup_collections = [collection_name_from_file(p) for p in files]

        # Try to load collection metadata (optional). This file is written by the
        # backup script as `collections_metadata.json` and contains options such as
        # timeseries and validators per collection. It's best-effort: if absent or
        # malformed we proceed without metadata.
        metadata = {}
        meta_path = extract_dir / "collections_metadata.json"
        if meta_path.exists():
            try:
                logger.info("Loading collection metadata from %s", meta_path)
                with meta_path.open("r", encoding="utf-8") as fh:
                    metadata = json_util.loads(fh.read()) or {}
            except Exception:
                logger.exception("Failed to load collection metadata; continuing without it")

        client = MongoClient(mongo_uri)
        db = client[mongo_db]

        current_collections = set(db.list_collection_names())
        backup_set = set(backup_collections)

        to_drop = sorted(list(current_collections - backup_set))
        to_create = sorted(list(backup_set - current_collections))
        to_restore = sorted(list(backup_set))

        # Summary
        summary_lines = ["Rollback summary:"]
        summary_lines.append(f"Target DB: {mongo_db} ({mongo_uri})")
        summary_lines.append(f"Archive: {args.archive}")
        summary_lines.append("")
        summary_lines.append(f"Collections to drop ({len(to_drop)}): {to_drop}")
        summary_lines.append(f"Collections to create ({len(to_create)}): {to_create}")
        summary_lines.append(f"Collections to restore ({len(to_restore)}): {to_restore}")
        if skipped_buckets:
            summary_lines.append("")
            summary_lines.append(f"Skipped internal bucket files ({len(skipped_buckets)}): {[p.name for p in skipped_buckets]}")
        summary = "\n".join(summary_lines)

        if args.dry_run:
            print(summary)
            logger.info("Dry-run requested; exiting without modifying database.")
            return

        if not confirm_action(summary, args.yes):
            logger.info("User declined to proceed. Exiting.")
            return

        # Validators (best-effort)
        validators = get_collection_validators(db)

        modified_validators = {}
        if args.force:
            # disable validators for collections present in backup (best-effort)
            modified_validators = disable_validators(db, to_restore)

        # Pre-restore snapshot: create a backup of the current target DB so we can
        # revert if the restore produces an unexpected state. This is enabled by
        # default but can be skipped with --no-snapshot.
        if not args.no_snapshot:
            if backup_database is None:
                logger.warning("Backup helper not available in runtime; cannot take pre-restore snapshot")
            else:
                snap_dir = Path(args.snapshot_dir) if args.snapshot_dir else Path("backup_dtb")
                try:
                    logger.info("Taking pre-restore snapshot of target DB to %s", snap_dir)
                    snap_archive = backup_database(mongo_uri=mongo_uri, db_name=mongo_db, out_root=snap_dir)
                    logger.info("Pre-restore snapshot created: %s", snap_archive)
                except Exception:
                    logger.exception("Failed to take pre-restore snapshot.")
                    logger.error("Aborting restore to avoid destructive changes without a snapshot. Use --no-snapshot to override.")
                    return

        # Determine whether inference is enabled (default ON unless explicitly disabled)
        inference_enabled = not getattr(args, 'no_infer_timeseries', False)

        # If requested, drop and recreate collections that are present in the backup
        # to ensure we have an exact snapshot restore. This prevents duplicate-key
        # errors when documents with the same _id already exist in the target DB.
        if args.replace_existing:
            logger.info("--replace-existing specified: dropping and recreating collections from backup before insert")
            for name in to_restore:
                try:
                    if name in db.list_collection_names():
                        logger.info("Dropping existing collection (replace): %s", name)
                        db.drop_collection(name)
                except Exception:
                    logger.exception("Failed to drop existing collection %s during replace; continuing", name)

                # Recreate collection using metadata if available (e.g., timeseries)
                coll_options = metadata.get(name) or {}
                if "timeseries" in coll_options:
                    ts_opts = coll_options.get("timeseries")
                    try:
                        logger.info("Creating time-series collection %s with options %s (replace)", name, ts_opts)
                        db.create_collection(name, timeseries=ts_opts)
                    except Exception:
                        logger.exception("Failed to create time-series collection %s during replace; creating normal collection", name)
                        try:
                            db.create_collection(name)
                        except Exception:
                            logger.debug("Create collection %s: ignored (may already exist)", name)
                else:
                    # If there was an internal bucket file for this logical collection,
                    # prefer recreating as a time-series. Map system.buckets.<collname>
                    # -> <collname> by checking skipped_buckets names.
                    created = False
                    if inference_enabled:
                        # bucket-based detection
                        bucket_name = f"system.buckets.{name}"
                        if any(p.stem == bucket_name for p in skipped_buckets):
                            # we don't have metadata, but the presence of bucket data in the
                            # archive strongly suggests this is a time-series collection.
                            # Try to infer options from data file if present, otherwise use
                            # sensible defaults.
                            candidate = next((p for p in files if collection_name_from_file(p) == name), None)
                            inferred = None
                            if candidate:
                                inferred = infer_timeseries_options_from_jsonl(candidate)
                            if inferred is None:
                                inferred = {"timeField": "ts", "metaField": "meta", "granularity": "hours"}
                            try:
                                logger.info("Creating inferred time-series collection %s with options %s (replace)", name, inferred)
                                db.create_collection(name, timeseries=inferred)
                                created = True
                            except Exception:
                                logger.exception("Failed to create inferred time-series collection %s; falling back", name)

                    if not created:
                        try:
                            logger.info("Creating collection %s (replace)", name)
                            db.create_collection(name)
                        except Exception:
                            logger.debug("Create collection %s (replace) ignored; may already exist", name)

        # Drop collections that shouldn't exist
        for name in to_drop:
            try:
                logger.info("Dropping collection: %s", name)
                db.drop_collection(name)
            except Exception:
                logger.exception("Failed to drop collection %s", name)

        # Restore collections
        results = {}
        for file_path in files:
            name = collection_name_from_file(file_path)
            # ensure collection exists (create by inserting)
            if name in to_create:
                # If we have metadata and it specifies a timeseries option, create the
                # collection using those options so MongoDB creates the internal
                # system.buckets collection correctly.
                coll_options = metadata.get(name) or {}
                if "timeseries" in coll_options:
                    ts_opts = coll_options.get("timeseries")
                    logger.info("Creating time-series collection %s with options %s", name, ts_opts)
                    try:
                        # Ensure any existing collection is removed first to avoid
                        # conflicts when re-creating as timeseries.
                        try:
                            if name in db.list_collection_names():
                                db.drop_collection(name)
                        except Exception:
                            logger.debug("Ignoring pre-create drop failure for %s", name)
                        db.create_collection(name, timeseries=ts_opts)
                    except Exception:
                        logger.exception("Failed to create time-series collection %s; falling back to normal create", name)
                        try:
                            db.create_collection(name)
                        except Exception:
                            logger.debug("Create collection %s: ignored (may already exist)", name)
                else:
                    # Try inference by default (unless opt-out) using bucket presence or data sample
                    created = False
                    if inference_enabled:
                        # bucket-based detection (preferred)
                        bucket_name = f"system.buckets.{name}"
                        if any(p.stem == bucket_name for p in skipped_buckets):
                            candidate = next((p for p in files if collection_name_from_file(p) == name), None)
                            inferred = None
                            if candidate:
                                inferred = infer_timeseries_options_from_jsonl(candidate)
                            if inferred is None:
                                inferred = {"timeField": "ts", "metaField": "meta", "granularity": "hours"}
                            try:
                                logger.info("Creating inferred time-series collection %s with options %s", name, inferred)
                                # Remove existing collection before creating timeseries
                                try:
                                    if name in db.list_collection_names():
                                        db.drop_collection(name)
                                except Exception:
                                    logger.debug("Ignoring pre-create drop failure for %s", name)
                                db.create_collection(name, timeseries=inferred)
                                created = True
                            except Exception:
                                logger.exception("Failed to create inferred time-series collection %s; falling back to normal create", name)

                        else:
                            # No bucket file, try sample-based inference
                            candidate = next((p for p in files if collection_name_from_file(p) == name), None)
                            if candidate:
                                inferred = infer_timeseries_options_from_jsonl(candidate)
                                if inferred:
                                    try:
                                        logger.info("Creating inferred time-series collection %s with options %s", name, inferred)
                                        try:
                                            if name in db.list_collection_names():
                                                db.drop_collection(name)
                                        except Exception:
                                            logger.debug("Ignoring pre-create drop failure for %s", name)
                                        db.create_collection(name, timeseries=inferred)
                                        created = True
                                    except Exception:
                                        logger.exception("Failed to create inferred time-series collection %s; falling back", name)

                    if not created:
                        logger.info("Creating collection: %s", name)
                        try:
                            db.create_collection(name)
                        except Exception:
                            logger.debug("Create collection %s: ignored (may already exist)", name)

            logger.info("Restoring collection %s from %s", name, file_path)
            try:
                inserted, total = stream_insert_collection(db, name, file_path, batch_size=args.batch_size)
                results[name] = {"inserted": inserted, "file_count": total}
                logger.info("Restored %s: inserted=%d file_lines=%d", name, inserted, total)
            except Exception:
                logger.exception("Failed to restore collection %s", name)
                results[name] = {"inserted": 0, "file_count": None, "error": True}

        # Reapply validators if we disabled them
        validator_restore_results = {}
        if args.force and modified_validators:
            logger.info("Attempting to restore collection validators (may fail if documents violate schema)")
            validator_restore_results = restore_validators(db, modified_validators)

        # Verification: counts & sample hash
        verification = {}
        for file_path in files:
            name = collection_name_from_file(file_path)
            file_count = results.get(name, {}).get("file_count")
            db_count = db[name].count_documents({})
            sample_hash = sample_hash_of_file(file_path, sample_size=args.verify_sample_size)
            verification[name] = {"file_count": file_count, "db_count": db_count, "sample_hash": sample_hash}

        # Summary report
        logger.info("Rollback completed. Verification summary:")
        for name, v in verification.items():
            logger.info("%s: file_count=%s db_count=%s sample_hash=%s", name, v["file_count"], v["db_count"], v["sample_hash"])

        if validator_restore_results:
            logger.info("Validator restore results (None means success): %s", validator_restore_results)

    finally:
        # Cleanup
        if extract_dir and args.out_dir is None:
            try:
                shutil.rmtree(extract_dir)
                logger.debug("Removed temporary extraction dir: %s", extract_dir)
            except Exception:
                logger.exception("Failed to remove temporary extraction dir: %s", extract_dir)


if __name__ == "__main__":
    main()
