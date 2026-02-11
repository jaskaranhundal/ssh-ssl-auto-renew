# PRD: Automated SSL Certificate Renewal & Deployment System

- **Version**: 1.0
- **Status**: Draft
- **Author**: Mary, Business Analyst
- **Date**: 2026-02-10

---

## 1. Overview & Objective

This document outlines the requirements for an automated system to handle SSL certificate renewals and deployments for multiple Ubuntu servers. The primary goal is to create a secure, configuration-driven, and reliable "set-it-and-forget-it" utility for infrastructure management.

The system will use Let's Encrypt for certificate issuance (via the DNS-01 challenge), the IONOS API for DNS management, and SSH/SCP for secure deployment to Nginx web servers. The entire process must be runnable locally, via a cron job, or within a Docker container, ensuring flexibility and portability.

### 1.1. Core Problem

Managing SSL certificates manually across multiple servers is time-consuming, error-prone, and a security risk. An expired certificate can cause service downtime and loss of user trust. This system aims to eliminate that operational burden.

### 1.2. High-Level Goals

-   **Automate Renewals:** Automatically renew SSL certificates nearing expiration.
-   **Automate DNS:** Automatically create and remove DNS TXT records required for DNS-01 validation.
-   **Automate Deployment:** Securely deploy renewed certificates and reload web servers with zero downtime.
-   **Configuration-Driven:** Allow infrastructure changes (adding/removing servers or domains) by editing YAML files, with no code modification required.
-   **Secure by Design:** Adhere to security best practices, especially regarding credentials and remote access.

### 1.3. Non-Goals (Out of Scope)

-   A graphical user interface (UI) or dashboard.
-   Support for manual DNS updates.
-   Support for certificate providers other than Let's Encrypt.
-   Support for web servers other than Nginx.
-   Infrastructure provisioning (e.g., using Terraform or Ansible).

## 2. Epics & User Stories

### Epic 1: Core Renewal Engine

> As an Operator, I want the system to handle the entire Let's Encrypt renewal process automatically so that I don't have to manually issue certificates.

| ID      | User Story                                                                                                  | Acceptance Criteria                                                                                                                                                                                            |
| :------ | :---------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S-101** | As an Operator, I want the system to check the expiry date of existing certificates for specified domains.    | - The system correctly identifies the domain's certificate file. <br>- It parses the certificate and extracts the "Not After" date. <br>- It triggers a renewal if the expiry is within a configurable threshold (e.g., 30 days). |
| **S-102** | As an Operator, I want the system to use the IONOS API to create a `_acme-challenge` TXT record for validation. | - It authenticates with the IONOS API using credentials from environment variables. <br>- It successfully creates the required TXT record with the correct value provided by the ACME client. <br>- It logs the success or failure of the API call. |
| **S-103** | As an Operator, I want the system to wait for DNS propagation before proceeding with the ACME challenge.       | - The system periodically queries DNS for the TXT record. <br>- It proceeds only after the record is successfully resolved from a public DNS server. <br>- It times out with an error after a configurable number of retries.    |
| **S-104** | As an Operator, I want the system to complete the Let's Encrypt challenge and receive the new certificate.    | - The system invokes an ACME client (e.g., `certbot`, `acme.sh`). <br>- Let's Encrypt successfully validates the TXT record. <br>- The new certificate and private key files are saved to a designated location.            |
| **S-105** | As an Operator, I want the system to clean up by removing the `_acme-challenge` TXT record after renewal.     | - It authenticates with the IONOS API. <br>- It successfully removes the TXT record created in S-102. <br>- It logs the result of the cleanup operation.                                                            |

---

### Epic 2: Configuration-Driven Management

> As an Operator, I want to manage all servers, domains, and credentials through external configuration files so that I can modify the infrastructure without changing the automation scripts.

| ID      | User Story                                                                                            | Acceptance Criteria                                                                                                                                                                                                |
| :------ | :---------------------------------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S-201** | As an Operator, I want to define all target servers in a `servers.yaml` file.                         | - The script successfully parses `servers.yaml`. <br>- The file format supports fields for `host`, `user`, `ssh_key_path`, and `nginx_reload_command`. <br>- The system can iterate through the list of defined servers.      |
| **S-202** | As an Operator, I want to map domains to target servers in a `domains.yaml` file.                       | - The script successfully parses `domains.yaml`. <br>- The file format supports a list of domains and, for each, a list of server names (which correspond to entries in `servers.yaml`).                                   |
| **S-203** | As an Operator, I want to provide all API keys and secrets via environment variables.                 | - The script reads IONOS API credentials (`IONOS_API_KEY`, `IONOS_API_SECRET`) from environment variables. <br>- No secrets are present in any YAML files or scripts. <br>- An `.env.example` file documents all required variables. |
| **S-204** | As an Operator, I want to define DNS provider settings in an `ionos.yaml` file.                         | - The script successfully parses `ionos.yaml`. <br>- The file format supports fields for API endpoint, TTL settings, etc.                                                                                              |

---

### Epic 3: Secure Deployment & Service Reload

> As an Operator, I want the renewed certificates to be securely deployed to the correct servers and for Nginx to be reloaded gracefully to apply the changes.

| ID      | User Story                                                                                              | Acceptance Criteria                                                                                                                                                                                                                              |
| :------ | :------------------------------------------------------------------------------------------------------ | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S-301** | As an Operator, I want the system to use SSH/SCP to copy the renewed certificate files to target servers. | - The system uses key-only SSH authentication. <br>- It securely copies the certificate and private key to the path defined for that server in `servers.yaml`. <br>- File permissions on the remote server are set securely (e.g., private key readable only by root). |
| **S-302** | As an Operator, I want the system to validate the Nginx configuration on the remote server before reloading. | - The system remotely executes `nginx -t`. <br>- If the configuration test fails, the deployment is aborted for that server. <br>- The newly deployed certificate files are rolled back (removed or replaced with the previous version).      |
| **S-303** | As an Operator, I want the system to gracefully reload Nginx to apply the new certificate.                | - The system remotely executes the `nginx_reload_command` from `servers.yaml`. <br>- The reload must not cause downtime for existing connections. <br>- The command's success or failure is logged.                                            |
| **S-304** | As an Operator, I want the system to run a health check after reloading Nginx to confirm success.         | - The system makes an HTTPS request to the renewed domain. <br>- It checks for a 2xx/3xx status code. <br>- It verifies the new certificate is being served (by checking the serial number or expiry date).                                |

---

### Epic 4: Operational Readiness & Portability

> As an Operator, I want to run the automation from anywhere (my laptop, a server, or a CI/CD pipeline) and have clear logs and operational controls.

| ID      | User Story                                                                                         | Acceptance Criteria                                                                                                                                                                                            |
| :------ | :------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **S-401** | As an Operator, I want to run the entire system inside a Docker container.                           | - A `Dockerfile` is provided that sets up all dependencies (ACME client, scripting runtime, etc.). <br>- The container can be built and run successfully. <br>- It correctly mounts volumes for configuration, logs, and certificates. |
| **S-402** | As an Operator, I want to be able to schedule the automation using a standard cron job.               | - A `cron.example` file is provided showing how to schedule the script to run periodically (e.g., daily). <br>- The example demonstrates how to handle environment variables and logging.                             |
| **S-403** | As an Operator, I want detailed, timestamped logs for every run.                                     | - All actions, successes, and failures are logged to a central file or stdout. <br>- Log entries are timestamped. <br>- Error messages are clear and actionable.                                                    |
| **S-404** | As an Operator, I want to run the system in a "dry-run" mode to test configuration without making changes. | - A `--dry-run` flag is available. <br>- In dry-run mode, the system simulates all actions (API calls, SSH commands) but does not execute them. <br>- The logs clearly indicate that it is a dry run.                    |

---

## 3. Risk & Dependency Analysis

| Category      | Item                                 | Mitigation Strategy                                                                                                                                      |
| :------------ | :----------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dependency**  | Let's Encrypt API                    | - Use a well-maintained ACME client. <br>- Implement retry logic for transient network failures. <br>- Monitor Let's Encrypt status pages for outages.        |
| **Dependency**  | IONOS DNS API                        | - Implement robust error handling and logging for all API calls. <br>- Ensure the script is resilient to minor API changes. <br>- Have a manual recovery plan documented. |
| **Dependency**  | SSH access to target servers         | - Use a dedicated, locked-down SSH key for automation. <br>- Ensure firewall rules permit access from the automation host. <br>- Log all SSH connection failures.  |
| **Risk**        | Nginx reload failure causes downtime | - **High Priority:** Implement `nginx -t` pre-flight check (S-302). <br>- Implement automated rollback of certificate files if the config test fails.          |
| **Risk**        | DNS propagation delay                | - Implement a retry loop with exponential backoff when checking for the TXT record (S-103). <br>- Make the retry count and delay configurable.               |
| **Risk**        | Leaked API credentials               | - **High Priority:** Strictly enforce the use of environment variables for all secrets (S-203). <br>- Add `*.env` and secrets files to `.gitignore`.         |
| **Risk**        | Partial deployment failure           | - The script must be designed to continue to the next server/domain if one fails. <br>- The final log summary must clearly list all successes and failures. |
| **Risk**        | Filesystem/permission errors         | - Ensure the automation script has the necessary read/write permissions for certificate storage and logs. <br>- The Docker setup should clearly define user/permissions. |

---

## 4. Delivery Milestones

| Milestone | Name                                  | Key Deliverables                                                                                                              |
| :-------- | :------------------------------------ | :---------------------------------------------------------------------------------------------------------------------------- |
| **M1**      | **Core Engine Proof of Concept**      | - Script to renew a single hardcoded domain using DNS-01 and IONOS API. <br>- Basic logging. (Completes Epic 1 for one case).   |
| **M2**      | **Configuration-Driven Logic**        | - Integration of `servers.yaml` and `domains.yaml`. <br>- Script can loop through all configured items. (Completes Epic 2).    |
| **M3**      | **Secure Deployment & Service Reload**  | - SSH/SCP deployment logic. <br>- Nginx validation and reload commands. <br>- Health checks. (Completes Epic 3).            |
| **M4**      | **Operational Readiness & Finalization** | - Dockerfile and cron job examples. <br>- Dry-run mode and comprehensive logging. <br>- Full README documentation. (Completes Epic 4). |

---

## 5. Definition of Done

The project is considered "Done" when all of the following criteria are met:

1.  All user stories across all four epics are implemented and meet their acceptance criteria.
2.  The system successfully and automatically renews a certificate for a test domain, deploys it to a test server, and reloads Nginx without error.
3.  A new server and domain can be added to the system by **only** editing `servers.yaml` and `domains.yaml`.
4.  The entire process runs successfully from start to finish inside the provided Docker container.
5.  All potential failures identified in the risk analysis are handled gracefully and logged clearly.
6.  The `README.md` provides complete setup, configuration, and recovery instructions.
