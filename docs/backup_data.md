
---
title: backup_data.py — MongoDB backup guide
---

# backup_data.py

This document describes `backup_dtb/backup_data.py`, a small Python utility to back up a MongoDB database into newline-delimited JSON files (JSON Lines) and package them into a `.tar` archive.

## Purpose

- Export all collections from a configured MongoDB database into individual JSON Lines files.
- Place collection files into a timestamped directory, then create a `.tar` archive containing those files.
- Intended for manual runs or scheduled tasks; each run produces a unique timestamped output so runs are safe to repeat.

## Quick start

1. Provide configuration via environment variables or a `.env` file: `MONGO_URI` and `MONGO_DB`.
2. Run:

```
python backup_dtb/backup_data.py
```

Optional arguments:

- `--out-dir`: Root directory to place backups (default: `backup_dtb`).
- `--pretty`: Pretty-print JSON (adds indentation). Note: output is still written as JSON Lines; pretty mode may embed newlines inside objects.
- `--mongo-uri`: Override `MONGO_URI` from the environment.
- `--mongo-db`: Override `MONGO_DB` from the environment.

Example (Windows PowerShell):

```powershell
$env:MONGO_URI = 'mongodb://user:pass@host:27017'
$env:MONGO_DB = 'mydatabase'
python .\backup_dtb\backup_data.py --out-dir .\backup_dtb --pretty
```

## Environment variables / configuration

- MONGO_URI (required): MongoDB connection string. The script supports reading a `.env` file using `python-dotenv`.
- MONGO_DB (required): Database name to back up.

Do not commit `.env` files containing credentials. Use a `.env.sample` for examples if needed.

## Output format

- A timestamped folder is created under the `out_dir`: `{out_dir}/backup_{YYYYmmdd_HHMMSS}/` (UTC timestamp).
- Each collection is written to `{collection_name}.jsonl`.
- Each line is a JSON document (JSON Lines). Documents are serialized with `bson.json_util.dumps` so ObjectId, datetimes, and other BSON types are preserved.
- After files are written the script creates an archive at `{out_dir}/backup_data/{backup_folder_name}.tar` containing the collection files. By default the temporary folder `backup_{ts}` is removed after archiving to save space.

## Important behavior

- Streaming: the script uses a cursor with `batch_size=1000` to avoid loading whole collections into memory.
- Per-collection error handling: if a collection fails to read or write, the exception is logged and the script continues with the next collection.
- Cleanup: after successfully creating the archive the temporary folder is removed. If archiving fails the temp folder is retained for investigation.

## Logging and exit codes

- Uses Python `logging` at INFO level by default. Exceptions are logged with stack traces.
- Exit codes:
  - `0`: success (archive created or backup completed)
  - `1`: backup failed due to an unhandled exception
  - `2`: missing configuration (`MONGO_URI` or `MONGO_DB` not provided)

## Security notes

- Never log or commit full connection strings containing credentials.
- Use a MongoDB user with least privilege required (read-only if possible).
- On managed services (Atlas), avoid restricted cursor options like `no_cursor_timeout` which may be disallowed.

## Suggested enhancements

- Compress the archive (`.tar.gz`) to reduce storage usage.
- Support incremental backups using a timestamp / updatedAt field to avoid exporting entire collections every run.
- Add direct upload to object storage (S3, GCS) after archive creation.
- Add a resume mechanism or chunked export for very large collections.

## Testing & verification

- Quick smoke test:

```
python backup_dtb/backup_data.py --out-dir .\backup_dtb --mongo-uri "mongodb://localhost:27017" --mongo-db testdb
```

- Verify that an archive appears in `./backup_dtb/backup_data/` and that the contained `.jsonl` files are valid JSON Lines (use `bson.json_util.loads` or a simple JSON parser to validate).

## Integration points (extension hooks)

- The main function `backup_database(mongo_uri, db_name, out_root, pretty=False)` is importable and can be called programmatically from other scripts or services.
- To change output format (e.g., NDJSON with gzip), implement a small writer wrapper and reuse the existing archive flow.

## Design notes

- The script is intentionally simple and non-destructive: it exports data only and does not modify the database. It is suitable for scheduled backups or pre-migration snapshots.

---

If you want, I can also:

- Add a short reference entry in `README.md` pointing to this document.
- Add a small unit test for `parse_args`.
- Change the archive format to `.tar.gz` and update the script accordingly.

This document is the English version of the backup utility guide. Tell me which follow-up you'd like and I'll implement it.
