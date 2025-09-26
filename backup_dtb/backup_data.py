"""
backup_data.py

Purpose:
  Small, standalone script to backup all collections from the configured MongoDB
  database into a timestamped folder under the repository's `backup_dtb` directory.

Behavior:
  - Reads MONGO_URI and MONGO_DB from environment (supports dotenv file via python-dotenv).
  - Creates a folder `backup_dtb/backup_[YYYYmmdd_HHMMSS]` and writes one file per collection.
  - Each collection file is newline-delimited JSON (JSON Lines) using bson.json_util for
    proper ObjectId / datetime serialization.
  - Continues on per-collection errors and logs progress.

Usage:
  python backup_dtb/backup_data.py
  python backup_dtb/backup_data.py --out-dir ./backup_dtb --pretty

Notes:
  - This script is intentionally minimal and additive (no schema changes).
  - It avoids loading an entire collection into memory by streaming cursor results.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from bson import json_util
from dotenv import load_dotenv
from pymongo import MongoClient


logger = logging.getLogger("backup_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_config() -> dict:
    """Load MongoDB configuration from the environment.

    Returns:
        dict: keys: MONGO_URI, MONGO_DB
    """
    # Allow loading of a .env file in the repo root for convenience
    load_dotenv()

    mongo_uri = os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB")

    return {"MONGO_URI": mongo_uri, "MONGO_DB": mongo_db}


def make_backup_dir(base_dir: Path, time_format: str = "%Y%m%d_%H%M%S") -> Path:
    ts = datetime.utcnow().strftime(time_format)
    name = f"backup_{ts}"
    out = base_dir / name
    out.mkdir(parents=True, exist_ok=False)
    return out


def sanitize_filename(name: str) -> str:
    """Make a collection name safe for filenames."""
    # Replace os-specific separators and spaces
    return name.replace(os.path.sep, "_").replace(" ", "_")


def backup_database(mongo_uri: str, db_name: str, out_root: Path, pretty: bool = False) -> Path:
    """Backup all collections in `db_name` to a timestamped folder under `out_root`.

    Writes newline-delimited JSON files (one JSON document per line) using
    bson.json_util.dumps so ObjectId and datetimes are serialized correctly.

    Returns:
        Path: path to created backup folder
    """
    client = MongoClient(mongo_uri)
    db = client[db_name]

    backup_dir = make_backup_dir(out_root)
    logger.info("Created backup folder: %s", backup_dir)

    collection_names = db.list_collection_names()
    logger.info("Found %d collections", len(collection_names))

    for cname in collection_names:
        safe_name = sanitize_filename(cname)
        out_file = backup_dir / f"{safe_name}.jsonl"
        logger.info("Backing up collection %s -> %s", cname, out_file)

        try:
            with out_file.open("w", encoding="utf-8") as fp:
                # Avoid using no_cursor_timeout (Atlas tiers may disallow it).
                # Use a reasonable batch_size to stream results without holding a no-timeout cursor.
                cursor = db[cname].find({}, batch_size=1000)
                for doc in cursor:
                    if pretty:
                        json_txt = json_util.dumps(doc, indent=2)
                    else:
                        json_txt = json_util.dumps(doc)
                    # Write one document per line (JSON Lines). For pretty mode we still
                    # keep one JSON object per line (it will contain newlines).
                    fp.write(json_txt + "\n")
                try:
                    cursor.close()
                except Exception:
                    pass

        except Exception as exc:
            logger.exception("Failed to backup collection %s: %s", cname, exc)
            # Continue with remaining collections

    # Write collection metadata (options) so restore can recreate special collections
    try:
        metadata = {}
        # db.list_collections() yields info including 'options' which may contain
        # timeseries and validator definitions. Store these options per-collection.
        for info in db.list_collections():
            name = info.get("name")
            options = info.get("options", {}) or {}
            if options:
                metadata[name] = options

        if metadata:
            meta_file = backup_dir / "collections_metadata.json"
            logger.info("Writing collection metadata to %s", meta_file)
            # Use bson.json_util for any BSON types in options
            with meta_file.open("w", encoding="utf-8") as fh:
                fh.write(json_util.dumps(metadata))
    except Exception:
        logger.exception("Failed to write collection metadata; continuing without it")
    finally:
        try:
            client.close()
        except Exception:
            logger.debug("Client close failed or already closed")

    # Create archive directory under out_root/backup_data and write a .tar archive
    archive_dir = out_root / "backup_data"
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"{backup_dir.name}.tar"
    logger.info("Creating tar archive %s", archive_path)

    try:
        with tarfile.open(archive_path, "w") as tar:
            # add files from backup_dir to the tar root (no containing folder)
            for f in sorted(backup_dir.iterdir()):
                if f.is_file():
                    tar.add(f, arcname=f.name)

        logger.info("Archive created: %s", archive_path)

        # Optionally remove the unarchived folder to save space
        try:
            shutil.rmtree(backup_dir)
            logger.info("Removed temporary backup folder: %s", backup_dir)
        except Exception:
            logger.exception("Failed to remove temporary backup folder: %s", backup_dir)

    except Exception as e:
        logger.exception("Failed to create archive %s: %s", archive_path, e)

    logger.info("Backup completed: %s", archive_path)
    return archive_path


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MongoDB full-database backup to JSON Lines files")
    p.add_argument("--out-dir", default="backup_dtb", help="Root folder to place backups")
    p.add_argument("--pretty", action="store_true", help="Pretty-print JSON (may include newlines)")
    p.add_argument("--mongo-uri", default=None, help="Override MONGO_URI environment variable")
    p.add_argument("--mongo-db", default=None, help="Override MONGO_DB environment variable")
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    cfg = load_config()

    mongo_uri = args.mongo_uri or cfg.get("MONGO_URI")
    mongo_db = args.mongo_db or cfg.get("MONGO_DB")

    if not mongo_uri or not mongo_db:
        logger.error("MONGO_URI and MONGO_DB must be set (environment or .env). Aborting.")
        raise SystemExit(2)

    out_root = Path(args.out_dir).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    try:
        backup_database(mongo_uri=mongo_uri, db_name=mongo_db, out_root=out_root, pretty=args.pretty)
    except Exception as e:
        logger.exception("Backup failed: %s", e)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
