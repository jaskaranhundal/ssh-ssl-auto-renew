# Project Documentation: Automated SSL Certificate Renewal System

---

## 1. Overview (For Non-Technical & Executive Audiences)

### 1.1. The Problem

In today's digital landscape, SSL certificates are crucial for securing web traffic and maintaining user trust. However, these certificates have a limited lifespan and must be renewed periodically. Managing this process manually across multiple servers is:
-   **Time-Consuming**: Operators must track expiry dates and perform manual renewal and installation procedures.
-   **Error-Prone**: A missed renewal can lead to expired certificates, browser warnings, and a loss of user trust.
-   **A Security Risk**: An expired certificate can cause service downtime and create a negative perception of the organization's security posture.

### 1.2. Our Solution

This project provides a fully automated, "set-it-and-forget-it" system that handles the entire lifecycle of SSL certificates. Once configured, it operates without manual intervention to ensure that all web services remain secure and trusted.

### 1.3. Business Value

-   **Increased Security & Reliability**: Eliminates the risk of downtime caused by expired SSL certificates.
-   **Operational Efficiency**: Frees up valuable engineering and operational time by automating a repetitive, manual task.
-   **Reduced Risk**: Minimizes human error, ensuring a consistent and reliable security posture across all web-facing applications.
-   **Scalability**: Easily manages certificates for dozens or hundreds of domains and servers through simple configuration file changes.

---

## 2. Operator's Guide (For System Administrators & DevOps)

This section explains how to configure, run, and monitor the system.

### 2.1. How It Works

The system runs as a script that performs the following high-level steps:
1.  **Loads Configuration**: Reads your infrastructure setup from YAML files (`domains.yaml`, `servers.yaml`) and your secrets from environment variables (`.env` file).
2.  **Checks Expiry**: For each domain, it checks if the existing SSL certificate is nearing its expiration date.
3.  **Issues/Renews Certificate**: If renewal is needed, it automatically communicates with Let's Encrypt using the DNS-01 challenge method via the IONOS DNS API.
4.  **Deploys Certificate**: Securely copies the new certificate to all target servers specified for that domain.
5.  **Reloads Web Server**: Validates the web server's configuration with the new certificate and gracefully reloads it to activate the certificate without downtime.
6.  **Verifies & Reports**: Performs a health check to ensure the new certificate is active and then generates a detailed Markdown report summarizing the outcome of the entire run.

### 2.2. Getting Started

A detailed step-by-step guide is available in the main **[README.md](README.md)** file, which covers:
-   Prerequisites (Python, `acme.sh`).
-   How to install Python dependencies.
-   How to configure your `.env`, `domains.yaml`, and `servers.yaml` files.
-   How to execute the script for both live and dry runs.

### 2.3. Interpreting the Output

After each run, the system provides two key outputs:
-   **Log File (`renewal.log`)**: Contains detailed, timestamped logs of every action performed by the script. This is the primary source for in-depth troubleshooting.
-   **Markdown Report (`renewal_report.md`)**: A high-level summary of the run, designed for quick "at a glance" status checks. It clearly shows the overall status (SUCCESS, FAILURE), a summary of domains processed, and detailed information about any failures, including specific error messages.

### 2.4. Troubleshooting Common Issues

| Issue                                               | Likely Cause & Solution                                                                                                                                              |
| :-------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **"acme.sh is not installed or not in PATH"**       | The `acme.sh` dependency is missing from the system. Follow the official guide to install it. For dry runs, this error is simulated and can be ignored.                  |
| **"Missing critical environment variables"**        | The `.env` file is missing or does not contain required variables like `IONOS_API_KEY` or `ACME_EMAIL`. Ensure the `.env` file is correctly configured.                   |
| **"SSH connection to ... failed"**                  | - The SSH key is incorrect or not authorized on the target server. <br>- A firewall is blocking the connection. <br>- The host IP address or user is incorrect in `servers.yaml`. |
| **"Nginx configuration validation failed"**         | A syntax error exists in your Nginx configuration files on the remote server. SSH into the server and run `sudo nginx -t` to debug the issue.                           |
| **"Health check failed after Nginx reload"**        | The new certificate was not correctly applied by Nginx, or the web service failed to restart properly. Check the Nginx service status and logs on the remote server.      |

---

## 3. Developer's Guide (For Engineers & Contributors)

This section provides a technical overview for those looking to understand, maintain, or extend the project.

### 3.1. System Architecture & Technical Deep Dive

For a complete technical breakdown of the system architecture, a deep dive into each Python module, and detailed explanations of the DNS-01 challenge, deployment process, and error handling, please refer to the **[Technical Deep Dive](technical_deep_dive.md)** document.

### 3.2. CI/CD & DevOps

The project is designed for integration with GitLab CI/CD. The `.gitlab-ci.yml` file defines a pipeline that:
1.  **Builds** a Docker image containing all dependencies from the `Dockerfile`.
2.  **Tests** the application by running the `pytest` suite.
3.  **Renews** certificates on a schedule or via manual trigger, using CI/CD variables for secrets management and saving the log and report files as job artifacts.

### 3.3. Testing Strategy

The project has a comprehensive suite of unit tests. To understand the testing philosophy and learn how to run the test suite or add new tests, please refer to the **[Testing Strategy](testing_strategy.md)** document.

### 3.4. How to Contribute

1.  **Clone the Repository**: `git clone ...`
2.  **Create a Feature Branch**: `git checkout -b my-new-feature`
3.  **Install Dependencies**: `cd cert_automation && pip3 install -r requirements.txt`
4.  **Make Changes**: Implement your new feature or bug fix.
5.  **Write/Update Tests**: Add new unit tests for your feature in the `tests/` directory.
6.  **Run Tests**: Ensure all tests pass by running `pytest` from the project root.
7.  **Commit and Push**: `git commit ... && git push origin my-new-feature`
8.  **Create a Pull Request**: Open a pull request against the `dev` branch for review.

---

## 4. Appendix: Configuration Reference

### 4.1. Environment Variables (`.env`)

| Variable                 | Description                                                                                             | Default Value            |
| :----------------------- | :------------------------------------------------------------------------------------------------------ | :----------------------- |
| `IONOS_API_KEY`          | **Required.** Your API key for the IONOS account.                                                       | -                        |
| `ACME_EMAIL`             | **Required.** The email address to register with Let's Encrypt for expiry notifications.                  | -                        |
| `RENEWAL_THRESHOLD_DAYS` | *Optional.* Number of days before expiry to trigger a renewal.                                          | `30`                     |
| `ACME_HOME_DIR`          | *Optional.* Local path where `acme.sh` stores its data.                                                 | `/tmp/acme_home`         |
| `CERT_BASE_PATH`         | *Optional.* Local base directory where the script will store issued certificates.                         | `/tmp/certs`             |
| `REPORT_FILE_PATH`       | *Optional.* Path where the Markdown report will be saved.                                               | `renewal_report.md`      |
| `LOG_FILE_PATH`          | *Optional.* Path for the detailed script execution log file.                                            | `renewal.log`            |
| `LOG_LEVEL`              | *Optional.* Logging verbosity (`INFO`, `DEBUG`, `WARNING`, `ERROR`).                                    | `INFO`                   |

### 4.2. `domains.yaml` Structure

This file maps domains to the servers where their certificates should be deployed.

```yaml
domains:
  - domain: example.com
    servers:
      - webserver-01 # Must match a 'name' in servers.yaml
      - webserver-02
  
  - domain: private.example.com
    servers:
      - webserver-01
```

### 4.3. `servers.yaml` Structure

This file defines the connection details and commands for each target server.

```yaml
servers:
  - name: webserver-01
    host: 192.168.1.101 # IP address or resolvable hostname
    user: automation_user # User for SSH connection
    ssh_key_path: "/path/to/local/ssh/keys/automation_key" # Path to the SSH private key on the machine running the script
    nginx_reload_command: "sudo systemctl reload nginx" # Command to reload Nginx
    cert_path: "/etc/nginx/ssl" # Remote path on the target server to deploy certificates
```