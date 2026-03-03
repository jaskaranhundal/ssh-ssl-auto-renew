# Automated SSL Certificate Renewal & Deployment System

This project provides a "set-it-and-forget-it" utility for automatically renewing Let's Encrypt SSL certificates and deploying them to multiple servers. It is designed to be configuration-driven, secure, flexible, and operationally resilient.

The system primarily uses the **DNS-01 challenge** with the **IONOS DNS API** via `acme.sh` to issue certificates, meaning it does not need to expose any ports on the target servers.

## How It Works

The main orchestration script (`cert_automation/main.py`) performs the following steps:
1.  Loads server and domain configurations. For local development, it reads from `cert_automation/config/*.yaml` files. In a CI/CD environment, these are generated from environment variables.
2.  Loads sensitive credentials from environment variables.
3.  For each configured domain, it checks if the certificate is due for renewal.
4.  If renewal is needed, it orchestrates the `acme.sh` client to perform the Let's Encrypt DNS-01 challenge.
5.  Upon successful issuance, it securely deploys the new certificate and key to the configured target servers using SSH/SCP.
6.  During deployment, it validates the Nginx configuration, gracefully reloads Nginx, and performs health checks.
7.  Generates a detailed Markdown report summarizing the process.

---

## Getting Started (Local Development)

This setup is for running and testing the script on your local machine.

### 1. Prerequisites

-   Python 3.9+
-   `acme.sh`: Required for live runs. Follow the [official installation guide](https://github.com/acmesh-official/acme.sh). Not needed for `--dry-run` simulations.
-   SSH access with key-based authentication to your target servers.

### 2. Configuration

1.  **Navigate to the script directory**:
    ```bash
    cd cert_automation
    ```

2.  **Install Dependencies**:
    ```bash
    pip3 install -r requirements.txt
    ```

3.  **Create Local Configuration Files**:
    The `domains.yaml` and `servers.yaml` files are ignored by Git. Create them locally from the provided examples.
    ```bash
    cp config/servers.yaml.example config/servers.yaml
    cp config/domains.yaml.example config/domains.yaml
    ```
    -   Edit `config/servers.yaml` to define your target servers.
    -   Edit `config/domains.yaml` to map your domains to the servers.

4.  **Create Environment File (`.env`)**:
    Copy `.env.example` to `.env` and fill in your secrets. This file is also ignored by Git.
    ```bash
    cp .env.example .env
    ```
    You will need to provide:
    -   `IONOS_API_KEY`: Your API key for your IONOS account.
    -   `ACME_EMAIL`: The email address to register with Let's Encrypt.
    -   ... (and any other optional variables)

### 3. Execution

With all configuration in place, run the main script from within the `cert_automation/` directory:

```bash
# For a live run
python3 main.py

# For a dry run (simulates the process, useful for testing configuration)
python3 main.py --dry-run
```

---

## Production & CI/CD Configuration

In a production environment like GitLab CI/CD, you should **not** use `.yaml` or `.env` files directly. Instead, the pipeline uses GitLab CI/CD variables.

As configured in `.gitlab-ci.yml`, the pipeline will:
1.  Read the content for your configuration from protected, masked **File** type variables in your GitLab project settings.
2.  Create the `domains.yaml` and `servers.yaml` files inside the CI job at runtime.

**Required GitLab CI/CD Variables:**

Go to your GitLab project's `Settings -> CI/CD -> Variables` and create:

*   **`CI_DOMAINS_YAML`** (Type: `File`): Paste the entire content of your production `domains.yaml` file here.
*   **`CI_SERVERS_YAML`** (Type: `File`): Paste the entire content of your production `servers.yaml` file here.
*   **`IONOS_API_KEY_GITLAB`** (Type: `Variable`): Your IONOS API key.
*   **`ACME_EMAIL_GITLAB`** (Type: `Variable`): Your Let's Encrypt email.
*   **`SSH_PRIVATE_KEY_GITLAB`** (Type: `File`): Your private SSH key for server deployment.

---
