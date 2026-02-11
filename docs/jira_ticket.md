# Jira Ticket Update: SSL Automation - Core Engine & Configuration

**Title**: Feat: Implement Core Renewal Engine and Configuration for SSL Automation

---

## Description

This update covers the completion of the core functionalities for the Automated SSL Certificate Renewal System, as outlined in the project PRD.

-   **Epic 1 (Core Renewal Engine)**: The system can now automatically check for certificate expiry and issue new certificates using Let's Encrypt and the IONOS DNS-01 challenge. This is handled by a Python wrapper around the `acme.sh` command-line tool.

-   **Epic 2 (Configuration-Driven Management)**: The system is now fully configuration-driven. All domains and servers are managed via `domains.yaml` and `servers.yaml` files, and all secrets are handled via environment variables. The main script reads these configurations to process all specified domains.

A new feature has also been added to intelligently issue either a specific or wildcard certificate based on whether the target domain resolves to a public or private IP address.

## Acceptance Criteria Checklist

### Epic 1: Core Renewal Engine
-   [x] **S-101**: System checks the expiry date of existing certificates.
-   [x] **S-102**: System uses the IONOS API to create a `_acme-challenge` TXT record for validation (handled by `acme.sh` plugin).
-   [x] **S-103**: System waits for DNS propagation before proceeding with the ACME challenge (handled by `acme.sh`).
-   [x] **S-104**: System completes the Let's Encrypt challenge and receives the new certificate.
-   [x] **S-105**: System cleans up by removing the `_acme-challenge` TXT record after renewal (handled by `acme.sh`).

### Epic 2: Configuration-Driven Management
-   [x] **S-201**: All target servers are defined in a `servers.yaml` file.
-   [x] **S-202**: Domains are mapped to target servers in a `domains.yaml` file.
-   [x] **S-203**: All API keys and secrets are provided via environment variables.
-   [x] **S-204**: DNS provider settings are defined (handled via environment variables for `acme.sh`).

---

## Implementation Details

-   **Project Structure**: All scripts and configuration examples are located in the `cert_automation/` directory.
-   **Core Logic**: The `main.py` script orchestrates the process, iterating through domains defined in `config/domains.yaml`.
-   **ACME Client**: Certificate issuance is handled by wrapping the `acme.sh` tool, which provides robust support for the IONOS DNS-01 challenge via its `dns_ionos` plugin.
-   **Dependencies**: The system is built in Python 3 and requires `pyOpenSSL`, `PyYAML`, `python-dotenv`, and `dnspython`.

## Next Steps

-   **Epic 3**: Implement the secure deployment of certificates to target servers via SSH/SCP and the graceful reload of Nginx.
-   **Epic 4**: Focus on operational readiness, including Docker containerization, cron job examples, and a `--dry-run` mode.

---
