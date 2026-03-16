# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automated SSL certificate renewal and deployment system using Let's Encrypt (via acme.sh) with IONOS DNS-01 challenge. Certificates are issued locally inside a Docker container, then deployed over SSH to target Nginx servers and optionally to OpenStack OTC Elastic Load Balancers.

## Commands

### Local Development
```bash
# Install dependencies
pip install -r cert_automation/requirements.txt

# Run (from cert_automation/ directory with .env loaded)
python3 main.py              # Renew if due
python3 main.py --force      # Force renewal regardless of expiry
python3 main.py --dry-run    # Simulate without making changes
python3 main.py --dry-run --force  # Simulate forced renewal
```

### Testing & Linting
```bash
# Lint (only critical errors)
flake8 cert_automation/ --count --select=E9,F63,F7,F82 --show-source --statistics

# Run tests
export PYTHONPATH=$PYTHONPATH:$(pwd)/cert_automation
pytest tests/

# Security scans
pip-audit -r cert_automation/requirements.txt
bandit -r cert_automation/ -ll
```

### Docker
```bash
docker build -t ssl-auto-renew .
docker run --env-file cert_automation/.env \
  -v $(pwd)/cert_automation/config:/app/config \
  ssl-auto-renew --force
```

## Architecture

The entry point is `cert_automation/main.py`. It orchestrates the full pipeline: load config → check expiry → issue cert → deploy → health check → report.

**Module responsibilities:**

| Module | Role |
|--------|------|
| `config_loader.py` | Loads `domains.yaml` + `servers.yaml` with `${ENV_VAR}` expansion |
| `cert_manager.py` | Checks PEM expiry; renewal due if < 30 days remain |
| `acme_client_wrapper.py` | Wraps `acme.sh` CLI via subprocess; `--staging` in dry-run |
| `ionos_dns_client.py` | REST client for IONOS DNS API; creates `_acme-challenge` TXT records |
| `remote_deployer.py` | Paramiko SSH/SCP; atomic deploy with backup/rollback |
| `health_checker.py` | HTTPS status + cert expiry verification (minimum 85 days post-deploy) |
| `otc_elb_client.py` | OpenStack OTC ELB certificate upload and listener update |
| `report_generator.py` | Markdown report with per-domain/per-server results |
| `retry_decorator.py` | Exponential backoff decorator (5 attempts) used across all I/O modules |
| `dns_utils.py` | DNS propagation helpers |
| `logger.py` | Centralized logging to file + console |

**Deployment flow per domain:**
1. Check cert expiry (skip if not due, unless `--force`)
2. Run `acme.sh --issue` with IONOS DNS-01 hook
3. Store `fullchain.cer` + `domain.key` under `${CERT_BASE_PATH}/${domain}/`
4. For each server: backup existing → SCP upload → `nginx -t` → `systemctl reload nginx` → health check → remove backup (or rollback on failure)
5. If OTC ELB configured: upload to cloud + update listeners

**Exit codes:** `0` = all succeeded or skipped; `1` = any domain failed (CI-friendly).

## Configuration

- `cert_automation/config/domains.yaml` — domains and their target servers / OTC ELB mappings
- `cert_automation/config/servers.yaml` — SSH credentials, cert paths, reload commands
- `cert_automation/.env` — all secrets and paths (see `.env.example`)

**Critical env vars:** `ACME_EMAIL`, `IONOS_API_KEY`, `IONOS_API_SECRET`, `ACME_SH_CMD` (path to acme.sh binary).

## Docker Context

The Dockerfile runs as non-root user `certuser` (UID 1000). acme.sh is installed at `/home/certuser/.acme.sh` with a global symlink at `/usr/local/bin/acme.sh`. The `ACME_HOME_DIR` env var must point to `/home/certuser/.acme.sh` for acme.sh to locate its config.

## CI/CD Pipeline (`.gitlab-ci.yml`)

Stages: `lint → test → security → dry-run → build → renew`

- `build` pushes to SWR registry using baked-context approach (credentials injected at build time, not runtime)
- `scheduled_renewal` runs weekly via GitLab CI schedule; executes `docker run` with env vars from GitLab CI variables
- `dry_run_validation` runs `python3 main.py --dry-run` and archives the report as an artifact
