# Implementation Plan: Automated SSL Certificate Renewal System

- **Version**: 1.0
- **Status**: In Progress
- **Author**: Gemini CLI
- **Date**: 2026-02-10

---

## 1. Overview

This document outlines the implementation plan and status for the "Automated SSL Certificate Renewal & Deployment System" as defined in the `prd.md`. The project is being developed in Python and leverages external tools like `acme.sh` for ACME challenges.

The implementation is broken down by the epics defined in the PRD.

---

## 2. Implementation Status

### Epic 1: Core Renewal Engine

> As an Operator, I want the system to handle the entire Let's Encrypt renewal process automatically.

-   **Status**: ✅ **Completed**
-   **Milestone**: M1 (Core Engine Proof of Concept)

| User Story | ID      | Implementation Details                                                                                                                                                                                             |
| :--------- | :------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Check Expiry | **S-101** | ✅ Implemented in `cert_automation/cert_manager.py`. Uses `pyOpenSSL` to parse certificate expiry dates.                                                                                                            |
| Create/Delete TXT Record | **S-102**, **S-105** | ✅ `acme.sh` with the `dns_ionos` plugin handles this automatically. The Python wrapper passes the `IONOS_TOKEN` environment variable. A standalone `IonosDnsClient` was also built for potential custom DNS work. |
| Wait for Propagation | **S-103** | ✅ `acme.sh` has built-in DNS propagation checks. A standalone `dns_utils.py` was also created using `dnspython` for custom checks if needed.                                                                |
| Complete Challenge | **S-104** | ✅ Implemented in `cert_automation/acme_client_wrapper.py`. This module wraps `acme.sh` commands to issue certificates and store them in a specified location.                                            |

### Epic 2: Configuration-Driven Management

> As an Operator, I want to manage all servers, domains, and credentials through external configuration files.

-   **Status**: ✅ **Completed**
-   **Milestone**: M2 (Configuration-Driven Logic)

| User Story | ID      | Implementation Details                                                                                                                                                                                          |
| :--------- | :------ | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Define Servers | **S-201** | ✅ Created `config/servers.yaml.example`. The system is ready to use this data for deployment tasks (in Epic 3).                                                                                             |
| Map Domains to Servers | **S-202** | ✅ Created `config/domains.yaml.example`. The `main.py` orchestrator now loads this file and iterates through all configured domains.                                                                |
| Secrets via Env Vars | **S-203** | ✅ Implemented using `python-dotenv`. An `.env.example` file is provided. All secrets (IONOS API key, etc.) are loaded from the environment.                                                            |
| DNS Provider Settings | **S-204** | 🚧 **Partially Complete**. The PRD mentioned an `ionos.yaml` for this, but `acme.sh` and the current implementation use environment variables (`IONOS_TOKEN`). This can be added if more complex IONOS settings are needed. |

### Epic 3: Secure Deployment & Service Reload

> As an Operator, I want the renewed certificates to be securely deployed and Nginx to be reloaded gracefully.

-   **Status**: ❌ **Pending**
-   **Milestone**: M3

| User Story | ID      | Implementation Plan                                                                                                                                                                       |
| :--------- | :------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SCP Deployment | **S-301** | To be implemented using a Python SSH library like `paramiko` or `fabric`. The script will connect to the servers defined in `servers.yaml` and copy the certificate files.           |
| Nginx Validation | **S-302** | The SSH module will execute `nginx -t` on the remote server and check the command's output before proceeding with a reload.                                                          |
| Nginx Reload | **S-303** | The SSH module will execute the `nginx_reload_command` specified for each server in `servers.yaml`.                                                                                   |
| Health Check | **S-304** | After reload, an HTTPS request will be made to the domain to check the status code and verify the new certificate's details (e.g., expiry date).                                       |

### Epic 4: Operational Readiness & Portability

> As an Operator, I want to run the automation from anywhere and have clear logs and operational controls.

-   **Status**: ❌ **Pending**
-   **Milestone**: M4

| User Story | ID      | Implementation Plan                                                                                                                                                      |
| :--------- | :------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docker Container | **S-401** | A `Dockerfile` will be created to package the Python scripts, `acme.sh`, and all dependencies. It will be configured to run `main.py` when the container starts.    |
| Cron Job | **S-402** | A `cron.example` file will be created with an example command to run the script (either directly or via the Docker container) on a schedule.                              |
| Detailed Logging | **S-403** | Basic logging is in place. This will be enhanced to include more detailed context and potentially structured logging (e.g., JSON format) for easier parsing.         |
| Dry-Run Mode | **S-404** | A `--dry-run` command-line argument will be added to `main.py`. This will cause the script to log actions that would be taken without actually executing them.         |

---
