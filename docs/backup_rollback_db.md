
---
title: Backup & Restore Runbook (backup_data.py + rollback_data.py)
---

# Backup & Restore Runbook

This consolidated document describes both the backup flow (`backup_dtb/backup_data.py`) and the restore/rollback flow (`backup_dtb/rollback_data.py`). It provides operator instructions, safety checks, and notes on validator and time-series handling.

## Overview

- Backup: `backup_dtb/backup_data.py` exports each collection into newline-delimited JSON files (.jsonl) using `bson.json_util` to preserve BSON types, places them in a timestamped folder, and packages them into an archive under `backup_dtb/backup_data/`.
- Restore: `backup_dtb/rollback_data.py` extracts an archive and restores collections to a target database, dropping collections not present in the backup and inserting documents from the JSONL files.

Both scripts support reading configuration from a `.env` file via `python-dotenv` and accept command-line overrides.

## Quick start — Backup

1. Ensure `MONGO_URI` and `MONGO_DB` are configured via environment or `.env`.
2. Run the backup script (PowerShell example):

```powershell
python .\backup_dtb\backup_data.py
```

Options:
- `--out-dir` (default `backup_dtb`)
- `--pretty` (pretty-print JSON)
- `--mongo-uri` / `--mongo-db` (override env)

Output: a timestamped directory `{out_dir}/backup_{YYYYmmdd_HHMMSS}/` containing `.jsonl` files, plus an archive at `{out_dir}/backup_data/backup_{...}.tar`.

Notes:
- Files are written as JSON Lines; `bson.json_util.dumps` is used to ensure ObjectIds and datetimes are preserved.
- The backup streams data with a reasonable `batch_size` to avoid loading whole collections into memory.

## Quick start — Restore (rollback)

Restore script location: `backup_dtb/rollback_data.py`.

Dry-run and inspect:

```powershell
python .\backup_dtb\rollback_data.py .\backup_dtb\backup_data\backup_YYYYmmdd_HHMMSS.tar --dry-run
```

Perform restore (interactive confirmation will be required unless `--yes` is passed):

```powershell
python .\backup_dtb\rollback_data.py .\backup_dtb\backup_data\backup_YYYYmmdd_HHMMSS.tar
```

Important options:
- `--dry-run` — print summary only, no DB changes.
- `--force` — temporarily disable collection validators during import (use with extreme caution).
- `--yes` — skip interactive confirmation.
- `--batch-size` — number of documents per insert batch (default 1000).
- `--verify-sample-size` — number of docs per collection to sample-hash for verification.
- `--replace-existing` — drop and recreate collections from the backup before inserting. Use this to ensure the target DB matches the archive exactly (destructive for existing collections).
- `--no-infer-timeseries` — opt-out of automatic time-series inference. By default the restore will attempt to detect and recreate time-series collections when explicit metadata is missing.

Behavior summary:
- The script extracts the archive to a temp folder (or `--out-dir`).
- It computes three sets: collections to drop (present in DB but not in backup), collections to create (present in backup but not in DB), and collections to restore (present in backup).
- Collections not present in the backup are dropped.
- Collections present in the backup are created (if needed) and populated by streaming inserts from the `.jsonl` files.

## Time-series and system buckets

Time-series collections in MongoDB are backed by internal bucket collections named `system.buckets.<logical_name>`. Directly inserting into `system.buckets.*` will fail unless the logical collection was created as a time-series with the appropriate options (for example `timeField` and `metaField`).

How the scripts handle time-series today

- Backup: the current `backup_dtb/backup_data.py` writes logical collection `.jsonl` files for logical collections (e.g., `waqi_station_readings.jsonl`). When possible it also writes a `collections_metadata.json` file that contains per-collection options returned by `db.list_collections()` (this may include a `timeseries` entry and any `validator` options).

- Restore (automatic behavior):
  - If `collections_metadata.json` is present in the archive, the restore will use the explicit `timeseries` options found there to create the collection (recommended and exact).
  - If `collections_metadata.json` is missing (older archive), the restore will attempt to re-create time-series collections automatically (this is the default behavior). The script uses two signals in order of preference:
    1. Presence of an internal bucket file in the archive named `system.buckets.<logical_name>` — this is a strong signal that the logical collection was a time-series.
    2. Heuristic inference by sampling a small number of documents from the collection `.jsonl` file to detect typical time-series fields (for example a `ts` timestamp field and a `meta` object). If the heuristic matches, the restore will create the collection as a time-series using sensible defaults (e.g., `timeField: ts`, `metaField: meta`, `granularity: hours`).

Notes and caveats:

- Conversion limitation: MongoDB does not allow converting an existing non-time-series collection in-place into a time-series collection. If the target DB already contains a regular collection with the same name, the restore will insert into it unless you drop and recreate the collection first.

- To force recreation as time-series for collections that already exist in the target DB, run the restore with `--replace-existing` (the script will drop and recreate collections from the backup before inserting). The script takes a pre-restore snapshot by default (unless you use `--no-snapshot`) so you can revert if needed.

- Inference is heuristic and best-effort. It is enabled by default to simplify restoring older archives. If you prefer fully deterministic behavior, create a fresh backup (the current backup script writes `collections_metadata.json`) and restore from that archive so explicit options are used.

Operator guidance (recommended flows):

1. Preferred (explicit metadata): take a fresh backup using the current `backup_dtb/backup_data.py` (this writes `collections_metadata.json`) and restore from that archive. The restore will use explicit metadata and recreate time-series collections exactly.

2. Older archive without metadata: if you must restore an archive that lacks `collections_metadata.json`, run the restore with `--replace-existing --yes` and keep inference enabled (do not pass `--no-infer-timeseries`). The script will attempt to infer time-series collections (bucket presence or sample-based heuristic) and recreate them before inserting.

3. Manual approach: if you prefer to control time-series options explicitly, create the logical time-series collections manually on the target DB with the correct `timeseries` options, then run the restore (it will skip bucket files and insert into the logical collection).

## Validator handling

- The restore script reads current collection validators (best-effort). If `--force` is provided the script will attempt to disable validators using `collMod` before import and attempt to reapply them after import. Any errors reapplying validators are logged for manual triage.
- Warning: disabling validators is destructive — documents that violate the current schema may be inserted. Always inspect logs and re-run validation after import.

## Verification and idempotency

- After import the script performs simple verification per collection:
  - Compare `file_count` (lines in .jsonl) and `db_count` (documents in restored collection).
  - Compute a `sample_hash` for the first N documents in the JSONL file and report it alongside the DB state. This is a lightweight sanity check — not a cryptographic guarantee.
- Restoring the same archive twice is idempotent in intent: the script drops collections not present in the backup and re-inserts documents from the archive, so the resulting collection set and documents should be the same.

For stronger verification consider adding deterministic per-collection checksums (e.g., sorted key lists + hashed concatenation) or export counts to CSV for historical comparison.

## Safety checklist (must do before restore)

1. Confirm the target environment (staging vs production).
2. Notify stakeholders and schedule downtime if needed.
3. Create a fresh backup of the current production DB (run `backup_dtb/backup_data.py`) and store it securely.
4. Run `--dry-run` and review the planned drop/create/restore summary.
5. If proceeding, run without `--dry-run` and either interactively confirm or pass `--yes`.

## Troubleshooting

- If insert operations into `system.buckets.*` fail: skip those files (script does this), recreate the logical time-series collection with the right options, and restore logical collection documents instead.
- If `collMod` fails while disabling or re-enabling validators: inspect permissions and run the necessary `collMod` commands manually with an admin user.
- If imports fail due to memory/timeouts: reduce `--batch-size` and retry.

## Examples (PowerShell)

# Dry-run
```
python .\backup_dtb\rollback_data.py .\backup_dtb\backup_data\backup_20250926_073727.tar --dry-run
```

# Restore with validator bypass (dangerous)
```
python .\backup_dtb\rollback_data.py .\backup_dtb\backup_data\backup_20250926_073727.tar --force --yes
```

## Implementation notes & next steps

- Current restore script preserves BSON types using `bson.json_util.loads`.
- We skip internal bucket files to avoid timeseries bucket creation errors. Consider extending the backup to capture collection options (validators, time-series options) so restores can be fully automated.
- Suggested follow-ups (pick one):
  - Store collection metadata during backup and use it during restore to recreate validators and time-series collections.
  - Add `.tar.gz` support for smaller archive sizes.
  - Add automated integration tests that perform backup + restore on a staging fixture and validate key collections (counts and sample hashes).

---

If you'd like, I can now implement one of the follow-ups (metadata capture, tar.gz, or tests). Tell me which and I'll add the code and docs and run the quick smoke tests.
