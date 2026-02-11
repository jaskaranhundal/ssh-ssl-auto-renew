# Implementation Plan: Automated SSL Certificate Renewal & Deployment System

This document outlines a phased implementation plan for building the Automated SSL Certificate Renewal & Deployment System from scratch, based on the requirements defined in `prd.md`.

---

## Phase 1: Core Renewal Engine & Configuration

**Objective**: To build the foundational components of the system that can issue a certificate for a single, hardcoded domain. This phase focuses on getting the core ACME logic and configuration handling in place.

| Task ID | Task Description                                                                   | Key File(s) / Component(s)                                          | Acceptance Criteria                                                                                                         |
| :------ | :--------------------------------------------------------------------------------- | :------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------- |
| **1.1**   | **Project Scaffolding & Initial Setup**                                            | `cert_automation/`, `tests/`, `.gitignore`, `requirements.txt`      | - Git repository is initialized. <br>- Project structure is created. <br>- Python dependencies are defined.                     |
| **1.2**   | **Implement Centralized Logging**                                                  | `logger.py`                                                         | - `setup_logging()` function configures logging to both console and a file. <br>- Log level is configurable via an environment variable. |
| **1.3**   | **Implement Configuration Management**                                             | `config_loader.py`, `config/*.yaml.example`, `.env.example`         | - `load_yaml_config()` can parse `domains.yaml` and `servers.yaml`. <br>- Secrets are loaded from a `.env` file.        |
| **1.4**   | **Implement Certificate Expiry Logic**                                             | `cert_manager.py`, `tests/test_cert_manager.py`                     | - `is_certificate_due_for_renewal()` correctly determines if a certificate needs renewal based on a given threshold. <br>- Unit tests pass. |
| **1.5**   | **Create `acme.sh` Wrapper**                                                       | `acme_client_wrapper.py`, `tests/test_acme_client_wrapper.py`       | - A Python wrapper can successfully execute `acme.sh` commands. <br>- It handles success, failure, and `FileNotFoundError`. <br>- Unit tests with mocking pass. |
| **1.6**   | **Integrate Core Logic in `main.py`**                                              | `main.py`                                                           | - `main.py` can orchestrate the above components to issue a certificate for a single hardcoded domain.                    |

---

## Phase 2: Secure Deployment & Service Reload

**Objective**: To extend the system to securely deploy the issued certificates to target servers and gracefully reload Nginx.

| Task ID | Task Description                                                                   | Key File(s) / Component(s)                                          | Acceptance Criteria                                                                                                         |
| :------ | :--------------------------------------------------------------------------------- | :------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------- |
| **2.1**   | **Implement Remote Deployer Module**                                               | `remote_deployer.py`, `tests/test_remote_deployer.py`               | - `RemoteDeployer` class can connect to a remote server via SSH using key-based auth. <br>- It can upload files (SCP) and execute remote commands. <br>- Unit tests with `paramiko` mocking pass. |
| **2.2**   | **Implement Nginx Validation & Reload**                                            | `remote_deployer.py`                                                | - `validate_nginx_config()` remotely executes `nginx -t` and correctly parses the result. <br>- `reload_nginx()` executes the configured reload command. |
| **2.3**   | **Implement Post-Deployment Health Checks**                                        | `health_checker.py`                                                 | - `check_https_status()` verifies the domain is reachable over HTTPS. <br>- `verify_cert_expiry()` confirms the new certificate is being served. |
| **2.4**   | **Integrate Deployment into `main.py`**                                            | `main.py`                                                           | - `main.py` now iterates through configured domains and servers. <br>- It calls `deploy_certificate` for each target. |
| **2.5**   | **Implement Rollback Mechanism**                                                   | `deploy_certificate` function in `main.py`                          | - If deployment fails, the system attempts to restore the previous certificate and reload Nginx to prevent downtime.       |

---

## Phase 3: Operational Readiness & Resilience

**Objective**: To make the system robust, portable, and ready for production use.

| Task ID | Task Description                                                                   | Key File(s) / Component(s)                                          | Acceptance Criteria                                                                                                         |
| :------ | :--------------------------------------------------------------------------------- | :------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------- |
| **3.1**   | **Implement Dry-Run Mode**                                                         | `main.py`, `acme_client_wrapper.py`, `remote_deployer.py`           | - A `--dry-run` flag simulates the entire process without making any actual changes. <br>- Includes mocking for `acme.sh` if it's not installed. |
| **3.2**   | **Implement Retry Logic (Self-Healing)**                                           | `retry_decorator.py`, applied to relevant modules                   | - A retry decorator is created to handle transient failures. <br>- It is applied to network-facing functions (API calls, SSH commands). |
| **3.3**   | **Implement Comprehensive Reporting**                                              | `report_generator.py`, `tests/test_report_generator.py`             | - A detailed Markdown report is generated after each run, summarizing successes and failures. <br>- Unit tests pass. |
| **3.4**   | **Create Dockerfile**                                                              | `Dockerfile`                                                        | - A `Dockerfile` is created that packages the application and all its dependencies (`acme.sh`, Python libraries).        |
| **3.5**   | **Create GitLab CI/CD Pipeline**                                                   | `.gitlab-ci.yml`                                                    | - The pipeline automatically builds the Docker image and runs tests. <br>- A scheduled job is configured to run the certificate renewal process. |

---

## Phase 4: Documentation & Finalization

**Objective**: To ensure the project is well-documented and easy for others to use and contribute to.

| Task ID | Task Description                                                                   | Key File(s) / Component(s)                                          | Acceptance Criteria                                                                                                         |
| :------ | :--------------------------------------------------------------------------------- | :------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------- |
| **4.1**   | **Write User & Project Documentation**                                             | `README.md`, `docs/project_documentation.md`                        | - `README.md` provides a clear overview and quick start guide. <br>- `project_documentation.md` offers comprehensive details for all audiences. |
| **4.2**   | **Write Technical & Testing Documentation**                                        | `docs/technical_deep_dive.md`, `docs/testing_strategy.md`           | - Technical deep dive explains the architecture and code. <br>- Testing strategy explains how to run and add tests.         |
| **4.3**   | **Final Code Review & Cleanup**                                                    | Entire codebase                                                     | - Code is reviewed for quality, clarity, and adherence to conventions. <br>- `.gitignore` is finalized. <br>- All project files are committed. |