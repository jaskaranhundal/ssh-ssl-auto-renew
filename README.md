# Automated SSL Certificate Renewal & Deployment System

This project provides a "set-it-and-forget-it" utility for automatically renewing Let's Encrypt SSL certificates and deploying them to multiple servers. It is designed to be configuration-driven, secure, flexible, and operationally resilient.

The system primarily uses the **DNS-01 challenge** with the **IONOS DNS API** via `acme.sh` to issue certificates, meaning it does not need to expose any ports on the target servers.

## Project Status

-   **Version**: 1.0
-   **Status**: Complete

The project has been implemented based on the `prd.md`. The current implementation covers:
-   ✅ **Epic 1: Core Renewal Engine**: The system checks for certificate expiry, issues new certificates for all configured domains using `acme.sh`, and handles detailed error reporting.
-   ✅ **Epic 2: Configuration-Driven Management**: The system is fully driven by YAML configuration files for domains and servers, and environment variables for secrets.
-   ✅ **Epic 3: Secure Deployment & Service Reload**: Implemented secure SSH/SCP deployment of renewed certificates, Nginx configuration validation, graceful Nginx reloads, and post-deployment health checks. Includes robust rollback mechanisms.
-   ✅ **Epic 4: Operational Readiness & Portability**: Includes a `Dockerfile` for containerization, support for cron job scheduling, comprehensive logging, and a `--dry-run` mode with `acme.sh` mocking.

---

## How It Works

The main orchestration script (`cert_automation/main.py`) performs the following steps:
1.  Loads server and domain configurations from `cert_automation/config/`.
2.  Loads sensitive credentials and configuration parameters from an environment file (`.env`).
3.  For each configured domain, it checks if the domain resolves to a public or private IP address.
    -   If **private**, it will request a **wildcard certificate** (e.g., `*.private.example.com`).
    -   If **public**, it will request a **specific certificate** (e.g., `www.example.com`).
4.  It determines if the existing certificate for the domain is due for renewal.
5.  If renewal is needed, it orchestrates the `acme.sh` client (with retry logic) to perform the Let's Encrypt DNS-01 challenge via the IONOS DNS API.
6.  Upon successful certificate issuance, it securely deploys the new certificate and key to the configured target servers using SSH/SCP (with retry logic).
7.  During deployment, it validates the Nginx configuration, gracefully reloads Nginx, and performs health checks to confirm successful deployment and certificate activation.
8.  Robust error handling with rollback mechanisms ensures service stability during deployment failures.
9.  Generates a detailed Markdown report (`renewal_report.md`) summarizing the entire process.

---

## Getting Started

### 1. Prerequisites

-   Python 3.9+
-   `acme.sh`: You must install this tool on the system where you will run the script for **live runs**. Follow the official installation guide: [https://github.com/acmesh-official/acme.sh](https://github.com/acmesh-official/acme.sh). For `--dry-run` simulations, `acme.sh`'s presence is mocked, allowing the workflow to be tested without its actual installation.
-   SSH access with key-based authentication configured for your target servers for the `automation_user` specified in `servers.yaml`.

### 2. Configuration

1.  **Navigate to the script directory**:
    ```bash
    cd cert_automation
    ```

2.  **Install Dependencies**:
    ```bash
    pip3 install -r requirements.txt
    ```

3.  **Create Environment File (`.env`)**:
    Copy `.env.example` to `.env` and fill in your details.
    ```bash
    cp .env.example .env
    ```
    You will need to provide:
    -   `IONOS_API_KEY`: Your API key for your IONOS account.
    -   `ACME_EMAIL`: The email address to register with Let's Encrypt.
    -   `RENEWAL_THRESHOLD_DAYS`: (Optional) Number of days before expiry to trigger renewal (default: 30).
    -   `ACME_HOME_DIR`: (Optional) Path where `acme.sh` stores its data (default: `/tmp/acme_home`).
    -   `CERT_BASE_PATH`: (Optional) Local base directory for storing issued certificates (default: `/tmp/certs`).
    -   `REPORT_FILE_PATH`: (Optional) Path for the generated Markdown report (default: `renewal_report.md`).
    -   `LOG_FILE_PATH`: (Optional) Path for the detailed log file (default: `renewal.log`).
    -   `LOG_LEVEL`: (Optional) Logging verbosity (e.g., INFO, DEBUG, WARNING, ERROR) (default: INFO).

4.  **Configure Servers (`config/servers.yaml`)**:
    Copy `config/servers.yaml.example` to `config/servers.yaml` and define your target servers. Ensure `ssh_key_path` points to the correct location of your automation SSH private key.
    ```bash
    cp config/servers.yaml.example config/servers.yaml
    ```

5.  **Configure Domains (`config/domains.yaml`)**:
    Copy `config/domains.yaml.example` to `config/domains.yaml` and map your domains to the servers you defined.
    ```bash
    cp config/domains.yaml.example config/domains.yaml
    ```

### 3. Execution

With all configuration in place, run the main script from within the `cert_automation/` directory:

```bash
# For a live run (requires acme.sh installed and correct API keys)
python3 main.py

# For a dry run (simulates the process, useful for testing configuration)
python3 main.py --dry-run
```

After execution, a detailed Markdown report will be generated at the path specified by `REPORT_FILE_PATH` (default: `renewal_report.md`).

---

## Operational Readiness

### Scheduling with Cron

A `cron.example` file is provided in the project root, demonstrating how to schedule the script to run periodically (e.g., daily). Ensure your cron environment correctly sources the `.env` file or explicitly provides the necessary environment variables.

### Docker Containerization

A `Dockerfile` is included to build a custom Docker image containing all dependencies (`acme.sh`, Python libraries). This allows for consistent and reproducible execution within a containerized environment, ideal for CI/CD pipelines (e.g., GitLab CI/CD).

---

## Technical Deep Dive

For a comprehensive understanding of the system's architecture, module breakdown, technical design, error handling, and CI/CD integration, refer to the `docs/technical_deep_dive.md` document.