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

logger = logging.getLogger("rollback_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Load default configuration from .env if present.
load_dotenv()

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


@dataclass(frozen=True)
class RestorePlan:
    to_drop: List[str]
    to_create: List[str]
    to_restore: List[str]

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restore MongoDB database from a backup .tar archive (JSON Lines)."
    )
    parser.add_argument("archive", help="Path to backup archive (e.g. backup_YYYYmmdd_HHMMSS.tar)")
    parser.add_argument("--mongo-uri", default=None, help="Override MONGO_URI environment variable")
    parser.add_argument("--mongo-db", default=None, help="Override MONGO_DB environment variable")
    parser.add_argument("--out-dir", default=None, help="Optional extract dir (default: temp dir)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Insert batch size")
    parser.add_argument("--force", action="store_true", help="Temporarily disable validators while importing")
    parser.add_argument("--dry-run", action="store_true", help="Show summary only, do not modify DB")
    parser.add_argument("--yes", action="store_true", help="Answer yes to confirmation prompts")
    parser.add_argument("--verify-sample-size", type=int, default=100, help="Docs per collection to hash for verification")
    parser.add_argument("--no-snapshot", action="store_true", help="Do not take a pre-restore snapshot of the target DB")
    parser.add_argument("--snapshot-dir", default=None, help="Directory for the pre-restore snapshot (default: backup_dtb/rollback_snapshots)")
    parser.add_argument("--replace-existing", action="store_true", help="Drop and recreate collections from the backup before inserting")
    parser.add_argument("--infer-timeseries", action="store_true", help="(deprecated) explicitly enable timeseries inference")
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
    files: List[Path] = []
    skipped_buckets: List[Path] = []

    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix != ".jsonl":
            continue
        if path.stem.startswith("system.buckets."):
            logger.warning("Skipping internal time-series bucket file: %s", path.name)
            skipped_buckets.append(path)
            continue
        files.append(path)

    return files, skipped_buckets


def collection_name_from_file(path: Path) -> str:
    return path.stem


def load_collection_metadata(root: Path) -> Dict[str, dict]:
    meta_path = root / "collections_metadata.json"
    if not meta_path.exists():
        return {}

    try:
        logger.info("Loading collection metadata from %s", meta_path)
        with meta_path.open("r", encoding="utf-8") as handle:
            data = json_util.loads(handle.read()) or {}
        if isinstance(data, dict):
            return data
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

def get_collection_validators(db) -> Dict[str, dict]:
    validators: Dict[str, dict] = {}
    try:
        for info in db.list_collections():
            name = info.get("name")
            options = info.get("options", {}) or {}
            if "validator" in options:
                validators[name] = options["validator"]
    except Exception:
        logger.exception("Failed to list collection validators; proceeding without validator info")
    return validators


def disable_validators(db, names: List[str]) -> Dict[str, dict]:
    original: Dict[str, dict] = {}
    for name in names:
        try:
            info = db.command("listCollections", filter={"name": name})
            coll_info = info.get("cursor", {}).get("firstBatch", [])
            if coll_info:
                options = coll_info[0].get("options", {}) or {}
                validator = options.get("validator")
                if validator:
                    original[name] = validator
                    logger.info("Disabling validator for collection %s", name)
                    db.command({"collMod": name, "validator": {}, "validationLevel": "off"})
        except errors.OperationFailure:
            logger.exception("Failed to disable validator for %s; skipping", name)
        except Exception:
            logger.exception("Unexpected error disabling validator for %s; skipping", name)
    return original


def restore_validators(db, validators: Dict[str, dict]) -> Dict[str, Optional[Exception]]:
    results: Dict[str, Optional[Exception]] = {}
    for name, validator in validators.items():
        try:
            logger.info("Restoring validator for %s", name)
            db.command(
                {
                    "collMod": name,
                    "validator": validator,
                    "validationLevel": "strict",
                    "validationAction": "error",
                }
            )
            results[name] = None
        except Exception as exc:
            logger.exception("Failed to restore validator for %s: %s", name, exc)
            results[name] = exc
    return results


def stream_insert_collection(db, coll_name: str, file_path: Path, batch_size: int = 1000) -> Tuple[int, int]:
    collection = db[coll_name]
    inserted = 0
    total = 0
    batch: List[dict] = []

    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            total += 1
            doc = json_util.loads(line)
            batch.append(doc)
            if len(batch) >= batch_size:
                result = collection.insert_many(batch)
                inserted += len(result.inserted_ids)
                batch = []
        if batch:
            result = collection.insert_many(batch)
            inserted += len(result.inserted_ids)

    return inserted, total


def sample_hash_of_file(file_path: Path, sample_size: int = 100) -> str:
    digest = hashlib.sha256()
    seen = 0

    with file_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
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

def infer_timeseries_options_from_jsonl(file_path: Optional[Path], sample_size: int = 50) -> Optional[dict]:
    if not file_path:
        return None

    ts_count = 0
    meta_count = 0
    checked = 0

    try:
        with file_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                if checked >= sample_size:
                    break
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    obj = json_util.loads(line)
                except Exception:
                    continue
                checked += 1
                if "ts" in obj:
                    ts_count += 1
                if "meta" in obj and isinstance(obj.get("meta"), dict):
                    meta_count += 1
    except Exception:
        return None

    if checked == 0:
        return None

    ts_ratio = ts_count / checked
    meta_ratio = meta_count / checked
    if ts_ratio >= 0.6 and meta_ratio >= 0.4:
        return {"timeField": "ts", "metaField": "meta", "granularity": "hours"}
    if ts_ratio >= 0.8 and meta_ratio < 0.4:
        return {"timeField": "ts", "granularity": "hours"}
    return None


def timeseries_inference_enabled(args: argparse.Namespace) -> bool:
    if getattr(args, "no_infer_timeseries", False):
        return False
    if getattr(args, "infer_timeseries", False):
        return True
    return True


def determine_timeseries_options(
    name: str,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> Optional[dict]:
    options = metadata.get(name) or {}
    if "timeseries" in options:
        return options.get("timeseries")

    if not inference_enabled:
        return None

    bucket_name = f"system.buckets.{name}"
    candidate = next((path for path in files if collection_name_from_file(path) == name), None)

    if any(path.stem == bucket_name for path in skipped_buckets):
        inferred = infer_timeseries_options_from_jsonl(candidate)
        return inferred or {"timeField": "ts", "metaField": "meta", "granularity": "hours"}

    if candidate:
        return infer_timeseries_options_from_jsonl(candidate)

    return None


def create_collection_with_options(db, name: str, ts_options: Optional[dict], label: str = "") -> None:
    suffix = f" ({label})" if label else ""

    if ts_options:
        logger.info("Creating time-series collection %s with options %s%s", name, ts_options, suffix)
        try:
            if name in db.list_collection_names():
                try:
                    db.drop_collection(name)
                except Exception:
                    logger.debug("Ignoring pre-create drop failure for %s", name)
        except Exception:
            logger.debug("Failed to inspect existing collections before creating %s", name)
        try:
            db.create_collection(name, timeseries=ts_options)
            return
        except Exception:
            logger.exception("Failed to create time-series collection %s%s; falling back to normal create", name, suffix)

    logger.info("Creating collection %s%s", name, suffix)
    try:
        db.create_collection(name)
    except Exception:
        logger.debug("Create collection %s%s ignored; may already exist", name, suffix)


def prepare_collections_for_replace(
    db,
    names: Iterable[str],
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> None:
    logger.info("--replace-existing specified: dropping and recreating collections before insert")
    for name in names:
        try:
            if name in db.list_collection_names():
                logger.info("Dropping existing collection (replace): %s", name)
                db.drop_collection(name)
        except Exception:
            logger.exception("Failed to drop existing collection %s during replace; continuing", name)

        ts_options = determine_timeseries_options(name, metadata, inference_enabled, skipped_buckets, files)
        create_collection_with_options(db, name, ts_options, label="replace")

def drop_collections(db, names: Iterable[str]) -> None:
    for name in names:
        try:
            logger.info("Dropping collection: %s", name)
            db.drop_collection(name)
        except Exception:
            logger.exception("Failed to drop collection %s", name)


def ensure_collection_ready(
    db,
    name: str,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
    files: List[Path],
) -> None:
    try:
        existing = db.list_collection_names()
    except Exception:
        existing = []
    if name in existing:
        return

    ts_options = determine_timeseries_options(name, metadata, inference_enabled, skipped_buckets, files)
    create_collection_with_options(db, name, ts_options)


def restore_collections(
    db,
    files: List[Path],
    batch_size: int,
    metadata: Dict[str, dict],
    inference_enabled: bool,
    skipped_buckets: List[Path],
) -> Dict[str, dict]:
    results: Dict[str, dict] = {}
    for file_path in files:
        name = collection_name_from_file(file_path)
        ensure_collection_ready(db, name, metadata, inference_enabled, skipped_buckets, files)
        logger.info("Restoring collection %s from %s", name, file_path)
        try:
            inserted, total = stream_insert_collection(db, name, file_path, batch_size=batch_size)
            results[name] = {"inserted": inserted, "file_count": total}
            logger.info("Restored %s: inserted=%d file_lines=%d", name, inserted, total)
        except Exception:
            logger.exception("Failed to restore collection %s", name)
            results[name] = {"inserted": 0, "file_count": None, "error": True}
    return results


def verify_restore(db, files: List[Path], results: Dict[str, dict], sample_size: int) -> Dict[str, dict]:
    verification: Dict[str, dict] = {}
    for file_path in files:
        name = collection_name_from_file(file_path)
        file_count = results.get(name, {}).get("file_count")
        db_count = db[name].count_documents({})
        sample_hash = sample_hash_of_file(file_path, sample_size=sample_size)
        verification[name] = {"file_count": file_count, "db_count": db_count, "sample_hash": sample_hash}
    return verification

def take_pre_restore_snapshot(args: argparse.Namespace, mongo_uri: str, mongo_db: str) -> bool:
    if args.no_snapshot:
        return True
    if backup_database is None:
        logger.warning("Backup helper not available in runtime; cannot take pre-restore snapshot")
        return True

    snapshot_root = Path(args.snapshot_dir) if args.snapshot_dir else Path("backup_dtb")
    try:
        logger.info("Taking pre-restore snapshot of target DB to %s", snapshot_root)
        archive = backup_database(mongo_uri=mongo_uri, db_name=mongo_db, out_root=snapshot_root)
        logger.info("Pre-restore snapshot created: %s", archive)
        return True
    except Exception:
        logger.exception("Failed to take pre-restore snapshot.")
        logger.error("Aborting restore to avoid destructive changes without a snapshot. Use --no-snapshot to override.")
        return False


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    mongo_uri, mongo_db = load_config(args.mongo_uri, args.mongo_db)

    extract_dir: Optional[Path] = None
    try:
        extract_dir = extract_archive(args.archive, args.out_dir)
        files, skipped_buckets = list_backup_jsonl(extract_dir)
        metadata = load_collection_metadata(extract_dir)
        backup_names = [collection_name_from_file(path) for path in files]

        with MongoClient(mongo_uri) as client:
            db = client[mongo_db]
            plan = build_restore_plan(db, backup_names)
            summary = format_plan_summary(plan, skipped_buckets, mongo_uri, mongo_db, args.archive)

            if args.dry_run:
                print(summary)
                logger.info("Dry-run requested; exiting without modifying database.")
                return

            if not confirm_action(summary, args.yes):
                logger.info("User declined to proceed. Exiting.")
                return

            if args.force:
                validators = get_collection_validators(db)
                if validators:
                    logger.info("Found validators on collections: %s", list(validators.keys()))
                modified_validators = disable_validators(db, plan.to_restore)
            else:
                modified_validators = {}

            if not take_pre_restore_snapshot(args, mongo_uri, mongo_db):
                return

            inference_enabled = timeseries_inference_enabled(args)

            if args.replace_existing:
                prepare_collections_for_replace(
                    db,
                    plan.to_restore,
                    metadata,
                    inference_enabled,
                    skipped_buckets,
                    files,
                )

            drop_collections(db, plan.to_drop)

            results = restore_collections(
                db,
                files,
                args.batch_size,
                metadata,
                inference_enabled,
                skipped_buckets,
            )

            validator_restore_results: Dict[str, Optional[Exception]] = {}
            if args.force and modified_validators:
                logger.info("Attempting to restore collection validators (may fail if documents violate schema)")
                validator_restore_results = restore_validators(db, modified_validators)

            verification = verify_restore(db, files, results, args.verify_sample_size)

            logger.info("Rollback completed. Verification summary:")
            for name, info in verification.items():
                logger.info(
                    "%s: file_count=%s db_count=%s sample_hash=%s",
                    name,
                    info["file_count"],
                    info["db_count"],
                    info["sample_hash"],
                )

            if validator_restore_results:
                logger.info("Validator restore results (None means success): %s", validator_restore_results)

    finally:
        if extract_dir and args.out_dir is None:
            try:
                shutil.rmtree(extract_dir)
                logger.debug("Removed temporary extraction dir: %s", extract_dir)
            except Exception:
                logger.exception("Failed to remove temporary extraction dir: %s", extract_dir)


if __name__ == "__main__":
    main()
