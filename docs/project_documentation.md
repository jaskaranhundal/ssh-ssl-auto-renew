# Project Documentation: Automated SSL Certificate Renewal System

- **Version**: 1.0
- **Status**: In Progress
- **Author**: Gemini CLI
- **Date**: 2026-02-10

---

## 1. Project Overview

This system provides a "set-it-and-forget-it" utility for automatically renewing Let's Encrypt SSL certificates and deploying them to multiple Ubuntu servers running Nginx. It is designed to be configuration-driven, secure, and flexible, capable of running locally, via a cron job, or within a Docker container.

The core renewal process uses the DNS-01 challenge with the IONOS DNS API.

---

## 2. Architecture

The system is composed of several Python modules orchestrated by a main script, all located in the `cert_automation/` directory.

```
cert_automation/
├── config/
│   ├── domains.yaml.example
│   └── servers.yaml.example
├── .env.example
├── main.py                    # Main orchestrator script
├── config_loader.py           # Loads YAML configuration files
├── cert_manager.py            # Checks certificate expiry dates
├── ionos_dns_client.py        # Standalone client for IONOS DNS API
├── dns_utils.py               # Utilities for checking DNS propagation
└── acme_client_wrapper.py     # Wrapper for the acme.sh command-line tool
```

-   **`main.py`**: The entry point of the application. It loads configurations and iterates through domains to perform renewal checks and trigger issuance.
-   **`config/`**: Contains the YAML files that define the infrastructure (servers and domains).
-   **`.env` file**: (Created from `.env.example`) stores all secrets and sensitive configuration.
-   **`acme.sh`**: An external shell script (which must be installed on the system) that is called by the Python wrapper to handle all ACME protocol interactions, including the DNS-01 challenge.

---

## 3. Configuration

### 3.1. Environment Variables

Create a `.env` file in the `cert_automation/` directory based on `.env.example`. This file will store all secrets.

**Required Variables:**
-   `IONOS_API_KEY`: Your API key for the IONOS account.
-   `ACME_EMAIL`: The email address to register with Let's Encrypt.

**Optional Variables:**
-   `RENEWAL_THRESHOLD_DAYS`: Days before expiry to trigger a renewal (default: 30).
-   `ACME_HOME_DIR`: Directory to store `acme.sh` configuration (default: `/tmp/acme_home`).
-   `CERT_BASE_PATH`: Base directory to store the issued certificates (default: `/tmp/certs`).

### 3.2. Server Configuration

Create a `config/servers.yaml` file from the `servers.yaml.example`. This file defines the servers where certificates will be deployed.

```yaml
# config/servers.yaml
servers:
  - name: webserver-01
    host: 192.168.1.101
    user: automation_user
    ssh_key_path: "/path/to/ssh/keys/automation_key"
    nginx_reload_command: "sudo systemctl reload nginx"
    cert_path: "/etc/nginx/ssl"
```

### 3.3. Domain Configuration

Create a `config/domains.yaml` file from the `domains.yaml.example`. This file maps domains to the servers defined in `servers.yaml`.

```yaml
# config/domains.yaml
domains:
  - domain: example.com
    servers:
      - webserver-01
      - webserver-02
  
  - domain: private.example.com
    servers:
      - webserver-01
```

---

## 4. Execution

1.  **Install Dependencies**:
    ```bash
    cd cert_automation
    pip3 install -r requirements.txt
    ```

2.  **Install `acme.sh`**:
    Follow the official installation guide: [https://github.com/acmesh-official/acme.sh](https://github.com/acmesh-official/acme.sh)

3.  **Run the script**:
    From within the `cert_automation/` directory, run the main script.
    ```bash
    python3 main.py
    ```
    The script will read the configuration and process all defined domains.

---

## 5. Module Breakdown

-   **`main.py`**: Orchestrates the entire process. It loads configs, loops through domains, checks for renewal, and calls the ACME wrapper.
-   **`config_loader.py`**: A simple utility to load and parse YAML files (`servers.yaml`, `domains.yaml`) using `PyYAML`.
-   **`cert_manager.py`**: Contains `is_certificate_due_for_renewal()` which reads a certificate file and checks its expiry date against a threshold.
-   **`acme_client_wrapper.py`**: Provides a Python interface to the `acme.sh` shell script. It handles `register_acme_account()` and `issue_certificate()`, passing necessary environment variables like `IONOS_TOKEN`.
-   **`ionos_dns_client.py`**: A standalone client for the IONOS DNS API. While `acme.sh` handles DNS challenges internally, this client can be used for other DNS-related tasks or custom hooks.
-   **`dns_utils.py`**: A utility using `dnspython` to check for DNS record propagation on public DNS servers. This can be used for verification or custom hooks.

---
