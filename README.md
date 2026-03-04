# Automated SSL Certificate Renewal & Deployment System

This project provides a "set-it-and-forget-it" utility for automatically renewing Let's Encrypt SSL certificates and deploying them to multiple servers. It is designed to be configuration-driven, secure, flexible, and operationally resilient.

The system primarily uses the **DNS-01 challenge** with the **IONOS DNS API** via `acme.sh` to issue certificates, meaning it does not need to expose any ports on the target servers.

## How It Works

The main orchestration script (`cert_automation/main.py`) performs the following steps:
1.  Loads server and domain configurations from `cert_automation/config/*.yaml`.
2.  Loads sensitive credentials from environment variables (`.env`).
3.  For each configured domain, it checks if the certificate is due for renewal (default threshold is 30 days).
4.  If renewal is needed (or forced), it orchestrates `acme.sh` to perform the Let's Encrypt DNS-01 challenge.
5.  Upon successful issuance, it securely deploys the new certificate and key to the configured target servers using an atomic staging approach (upload to `/tmp` then `sudo mv`) to ensure reliability even with permission restrictions.
6.  During deployment, it validates the Nginx configuration, gracefully reloads Nginx, and performs health checks.
7.  Generates a detailed Markdown report summarizing the process.

---

## Getting Started (Local Development)

### 1. Prerequisites

-   Python 3.9+
-   `acme.sh`: Required for live runs.
-   SSH access with key-based authentication to your target servers.

### 2. Configuration

1.  **Navigate to the script directory**: `cd cert_automation`
2.  **Install Dependencies**: `pip3 install -r requirements.txt`
3.  **Create Configuration Files**:
    ```bash
    cp config/servers.yaml.example config/servers.yaml
    cp config/domains.yaml.example config/domains.yaml
    cp .env.example .env
    ```
4.  **Edit `.env`**:
    -   `IONOS_API_KEY`: Your IONOS API key.
    -   `IONOS_API_SECRET`: Your IONOS API secret.
    -   `ACME_EMAIL`: Your registration email.
    -   `ACME_SH_COMMAND`: Path to your `acme.sh` executable (e.g., `/Users/yourname/.acme.sh/acme.sh`).

### 3. Execution

```bash
# For a live run (only renews if due)
python3 main.py

# To force renewal immediately
python3 main.py --force

# For a dry run (simulation)
python3 main.py --dry-run --force
```

---

## Docker Execution

You can run the system using Docker to avoid local dependency issues:

```bash
docker build -t ssl-auto-renew .
docker run --env-file cert_automation/.env -v $(pwd)/cert_automation/config:/app/config ssl-auto-renew --force
```

---

## Production & CI/CD Configuration

In GitLab CI/CD, use **File** type variables for `CI_DOMAINS_YAML` and `CI_SERVERS_YAML`, and **Variable** type for `IONOS_API_KEY`, `IONOS_API_SECRET`, and `ACME_EMAIL`.
