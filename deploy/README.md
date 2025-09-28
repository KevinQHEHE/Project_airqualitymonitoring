# Deployment Toolkit

This directory contains the automation assets that provision and keep the Air Quality Monitoring stack up to date on an Ubuntu host. Everything else (application source, helper scripts, etc.) lives one level up.

## Files

- `universal-deploy.sh` – idempotent installer/upgrader. It installs packages, refreshes the Python environment, manages systemd + Nginx, can request Let’s Encrypt certificates, and restarts services. The script reads overrides from `deploy/env` if present.
- `health-check.sh` – quick probe that verifies `air-quality-monitoring` and `nginx` services plus the `/api/health` endpoint locally and (optionally) via the public URL. Good for CI or post-deploy smoke tests.
- `env` (ignored by Git) – per-server overrides. Copy `env.sample` and adjust values such as `PRIMARY_DOMAIN`, `SERVICE_PORT`, or `ENABLE_CERTBOT` before running the installer.

## Initial Deployment

1. `cp deploy/env.sample deploy/env` and fill in any secrets or domain names.
2. `chmod +x deploy/universal-deploy.sh`
3. `./deploy/universal-deploy.sh`

The script will:
- validate sudo access and system resources;
- fetch the latest Git revision (unless `--skip-git` or uncommitted changes are present);
- create/update the virtualenv and Python dependencies;
- write systemd + Nginx configuration;
- (optionally) request/renew Let’s Encrypt certificates when `ENABLE_CERTBOT=true` and DNS records are in place;
- restart services and run a Flask smoke test.

Logs stream to the console and are also written to `deploy_run.log` in the project root.

## Updating to a New Version

Any time you pull new code (or rerun on the server), execute:

```bash
./deploy/universal-deploy.sh --skip-tests
```

What happens:
- Git is fast-forwarded to `GIT_BRANCH`/`GIT_REMOTE` when the working tree is clean.
- Python dependencies are refreshed to match `requirements.txt`.
- Nginx/systemd configuration is regenerated to reflect any env changes.
- Services are restarted and health checks run (unless `--skip-tests`).

If you are actively editing files on the server, use `--skip-git` to avoid `git pull`, or commit/stash your changes before running the script.

## HTTPS & Domains

Set the following in `deploy/env` (or export before running):

```
PRIMARY_DOMAIN=airqualitymonitor.page
ADDITIONAL_DOMAINS="www.airqualitymonitor.page airqualitymonitor.me www.airqualitymonitor.me"
ENABLE_CERTBOT=true
CERTBOT_EMAIL=admin@airqualitymonitor.me
PUBLIC_URL=https://airqualitymonitor.page
```

On the first run the script serves HTTP while DNS/Certbot are being validated. Once a valid certificate exists, the script switches Nginx to HTTPS with an automatic HTTP?HTTPS redirect. Re-run `./deploy/universal-deploy.sh` after changing DNS/certificate settings.

## Quick Health Check

```bash
./deploy/health-check.sh
PUBLIC_URL=https://airqualitymonitor.page ./deploy/health-check.sh
```

The command exits non-zero if any probe fails, making it suitable for automation.

## Useful Flags

- `--skip-git` – keep the current working tree (no `git fetch/pull`).
- `--skip-tests` – skip the Flask smoke test stage (useful on slow VMs).
- `-h` / `--help` – show inline help.

These flags can be combined, e.g. `./deploy/universal-deploy.sh --skip-git --skip-tests`.

## Helper Scripts (generated at the project root)

- `status.sh` – report service state, ports, and recent logs.
- `restart.sh` – restart the app + Nginx services.
- `logs.sh` – tail the main logs.

Keep this directory focused on deployment artifacts; app-specific scripts belong elsewhere in the project.