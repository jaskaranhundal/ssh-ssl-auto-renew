# Automated SSL Certificate Renewal & Deployment System

A production-grade, security-first automation pipeline that manages the full lifecycle of Let's Encrypt SSL certificates — from issuance via DNS-01 challenge to zero-downtime deployment across multiple servers and cloud load balancers — with no manual intervention required.

Built with a security engineer's mindset: no open ports, verified host keys, atomic file staging, automatic rollback, and full CI/CD integration.

---

## Architecture Overview

```
GitLab CI/CD (Weekly Schedule)
        |
        v
[ Docker Container ]
        |
        |-- acme.sh (DNS-01 via IONOS API) --> Let's Encrypt CA
        |        |
        |        v
        |   Certificate Issued (wildcard + SAN supported)
        |
        |-- SSH (paramiko) with RejectPolicy + pre-scanned known_hosts
        |        |
        |        v
        |   Remote Server (atomic upload -> sudo mv -> nginx reload -> health check)
        |
        |-- OTC Keystone API
                 |
                 v
           OTC ELB Listener Updated (cloud load balancer)
```

**Key design decisions:**
- **DNS-01 challenge only** — no ports need to be opened on any server; the domain is validated via a temporary TXT record in the IONOS DNS API
- **RejectPolicy SSH** — host keys are pre-scanned by `ssh-keyscan` at pipeline time and baked into the container; unknown hosts are refused, not trusted blindly
- **Atomic staging** — certificates are uploaded to a UUID-named `/tmp` path and moved with `sudo mv`; partial writes never overwrite live certs
- **Automatic rollback** — if deployment or Nginx reload fails, the previous certificate is restored and Nginx is reloaded with the old cert
- **Baked-context image** — secrets (SSH key, config, known_hosts) are injected into an ephemeral Docker layer at pipeline runtime, bypassing volume mapping issues in CI

---

## Pipeline Stages

| Stage | Job | What it does |
|---|---|---|
| `lint` | `lint_python` | Flake8 syntax and error checks |
| `test` | `unit_tests` | Pytest unit tests with mocked SSH/ACME |
| `security` | `sca_scan` | `pip-audit` for known CVEs in dependencies |
| `security` | `sast_bandit` | Bandit SAST scan (CWE-295, B601, B108, etc.) |
| `dry-run` | `dry_run_validation` | Full simulation run — no real certs, no real SSH |
| `build` | `build` | Builds and pushes Docker image to OTC SWR registry |
| `renew` | `scheduled_renewal` | Weekly cert renewal run (or manual trigger on `main`) |

---

## Features

- **Zero-touch renewal** — certificates are checked weekly; only renewed when within the configured threshold (default 30 days before expiry)
- **Wildcard certificate support** — issues `*.example.com` via DNS-01; health checks automatically skip wildcard domains (not directly resolvable)
- **Multi-server deployment** — one cert can be deployed to multiple servers in parallel via SSH/SFTP
- **OTC ELB integration** — uploads renewed certificates directly to Open Telekom Cloud Elastic Load Balancer listeners via Keystone API
- **Dry-run mode** — simulates the full pipeline without contacting Let's Encrypt or any server; useful for testing config changes
- **Detailed Markdown reports** — every run generates a report with per-domain and per-server results

---

## Security Controls

| Control | Implementation |
|---|---|
| No open ports required | DNS-01 challenge via IONOS API |
| SSH host key verification | `RejectPolicy` + `ssh-keyscan` pre-population |
| No predictable temp file paths | UUID-prefixed staging path (mitigates CWE-377) |
| Secrets never in code or image layers | Injected via CI environment variables at runtime |
| Dependency vulnerability scanning | `pip-audit` in every pipeline |
| Static code security analysis | Bandit SAST (CWE-295, B601, B108) in every pipeline |
| Non-root container execution | `certuser` (UID 1000) runs the application |

---

## Getting Started

### Prerequisites

- Python 3.10+
- `acme.sh` installed (or use Docker)
- IONOS DNS API credentials
- SSH key with sudo access on target servers

### Local Setup

```bash
cd cert_automation
pip3 install -r requirements.txt

cp config/servers.yaml.example config/servers.yaml
cp config/domains.yaml.example config/domains.yaml
```

Create a `.env` file:

```env
ACME_EMAIL=you@example.com
IONOS_API_KEY=your_ionos_prefix
IONOS_API_SECRET=your_ionos_secret
ACME_SH_COMMAND=/home/youruser/.acme.sh/acme.sh
ACME_HOME_DIR=/home/youruser/.acme.sh
SSH_KEY_PATH=/home/youruser/.ssh/id_rsa
CERT_BASE_PATH=.certs
RENEWAL_THRESHOLD_DAYS=30
```

### Run

```bash
# Dry run — simulates everything, no real changes
python3 main.py --dry-run --force

# Live run — only renews if within threshold
python3 main.py

# Force renewal regardless of expiry
python3 main.py --force
```

### Docker

```bash
docker build -t ssl-auto-renew .
docker run --env-file cert_automation/.env \
  -v $(pwd)/cert_automation/config:/app/config \
  ssl-auto-renew --dry-run --force
```

---

## Configuration

### `config/domains.yaml`

```yaml
domains:
  - domain: "*.example.com"
    servers:
      - webserver-01
    otc_elb:
      listeners:
        - name: "https-listener"
          id: "listener-uuid-here"

  - domain: "admin.example.com"
    servers:
      - webserver-01
```

### `config/servers.yaml`

```yaml
servers:
  - name: webserver-01
    host: 10.0.0.9
    user: automation_user
    ssh_key_path: "/home/user/.ssh/id_rsa"
    nginx_reload_command: "sudo systemctl reload nginx"
    cert_path: "/etc/nginx/ssl"
```

---

## GitLab CI Variables Required

| Variable | Type | Description |
|---|---|---|
| `CI_DOMAINS_YAML` | File | `domains.yaml` content |
| `CI_SERVERS_YAML` | File | `servers.yaml` content |
| `SSH_PRIVATE_KEY_GITLAB` | File | Private SSH key for server access |
| `IONOS_API_KEY_GITLAB` | Variable | IONOS DNS API prefix |
| `IONOS_API_SECRET_GITLAB` | Variable | IONOS DNS API secret |
| `ACME_EMAIL_GITLAB` | Variable | Let's Encrypt account email |
| `TARGET_SSH_HOSTS_GITLAB` | Variable | Space-separated list of target server IPs (for `ssh-keyscan`) |
| `DOCKER_REGISTRY_USER` | Variable | OTC SWR registry username |
| `DOCKER_REGISTRY_PASSWORD` | Variable | OTC SWR registry password |
| `OS_AUTH_URL` | Variable | OTC Keystone auth URL |
| `OS_USERNAME` | Variable | OTC username |
| `OS_PASSWORD` | Variable | OTC password |
| `OS_USER_DOMAIN_NAME` | Variable | OTC user domain name |
| `OS_PROJECT_ID` | Variable | OTC project ID |

---

## Tech Stack

- **Python 3.10** — orchestration, SSH, API clients
- **acme.sh** — ACME protocol client (DNS-01 challenge)
- **Paramiko** — SSH/SFTP with host key verification
- **Docker** — containerized execution with non-root user
- **GitLab CI/CD** — automated pipeline with lint, test, security, dry-run, build, and renew stages
- **Open Telekom Cloud (OTC)** — target cloud environment (ELB, SWR registry)
- **IONOS DNS API** — DNS-01 challenge automation

---

## License

MIT
