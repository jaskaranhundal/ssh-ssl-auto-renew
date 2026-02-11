# Jira Tickets: Automated SSL Certificate Renewal & Deployment System

**Project Key**: SSLCERT  
**Created**: 2026-02-11  
**Last Updated**: 2026-02-11

---

## EPIC: SSLCERT-1
**Title**: Automated SSL Certificate Renewal & Deployment System  
**Type**: Epic  
**Priority**: High  
**Status**: In Progress  
**Labels**: infrastructure, automation, security, ssl, devops

### Epic Description
Build an automated system for SSL certificate management that handles the complete lifecycle of Let's Encrypt certificates across multiple Ubuntu servers running Nginx. Eliminates manual certificate management, reduces security risks, and prevents service downtime.

### Business Value
- **Operational Efficiency**: Saves ~4 hours/month per operations engineer
- **Risk Mitigation**: Prevents service outages from expired certificates (estimated cost: $50K per hour)
- **Security**: Enforces automated rotation of SSL certificates
- **Scalability**: Supports unlimited domains and servers through configuration files

### Acceptance Criteria
- [x] System automatically renews certificates 30 days before expiration
- [x] Zero downtime during certificate deployment and Nginx reload
- [x] All secrets managed via environment variables
- [ ] Complete rollback capability on deployment failures
- [ ] Docker containerization for portability
- [ ] Comprehensive logging and dry-run mode

---

## Core Implementation Tickets

### SSLCERT-10: Certificate Renewal Engine (Epic 1)
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ✅ Done  
**Priority**: Critical  
**Story Points**: 13  
**Sprint**: Sprint 1-2  
**Labels**: core-engine, letsencrypt, acme

#### User Story
As an Operator, I want the system to automatically handle the complete Let's Encrypt renewal process so that I don't have to manually issue certificates.

#### Acceptance Criteria
- [x] System checks certificate expiry dates using pyOpenSSL
- [x] Triggers renewal when certificate expires within configurable threshold (30 days)
- [x] Uses IONOS API via acme.sh to create/delete DNS TXT records
- [x] Waits for DNS propagation before proceeding with ACME challenge
- [x] Completes Let's Encrypt DNS-01 challenge and receives certificate
- [x] Saves certificate and private key to designated storage location
- [x] Cleans up DNS TXT records after successful issuance

#### Technical Implementation
- **Modules**: `cert_manager.py`, `acme_client_wrapper.py`, `dns_utils.py`, `ionos_dns_client.py`
- **ACME Client**: acme.sh with dns_ionos plugin
- **Challenge Type**: DNS-01
- **Certificate Storage**: `{CERT_BASE_PATH}/{domain}/fullchain.cer` and `domain.key`

#### Definition of Done
- Certificate expiry detection working correctly
- Let's Encrypt certificate issuance via DNS-01 successful
- All operations logged with timestamps
- Unit tests passing for certificate parsing

---

### SSLCERT-20: Configuration Management System (Epic 2)
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ✅ Done  
**Priority**: High  
**Story Points**: 8  
**Sprint**: Sprint 2-3  
**Labels**: configuration, yaml, security

#### User Story
As an Operator, I want to manage all servers, domains, and credentials through external configuration files so that I can modify infrastructure without changing code.

#### Acceptance Criteria
- [x] `servers.yaml` defines all target servers (host, user, SSH key, nginx commands, cert paths)
- [x] `domains.yaml` maps domains to target servers
- [x] All API keys and secrets loaded from environment variables
- [x] No secrets present in YAML files or code
- [x] `.env.example` documents all required variables
- [x] Configuration validation with clear error messages
- [x] Cross-reference validation (domains reference valid servers)

#### Technical Implementation
- **Modules**: `config_loader.py`, `main.py`
- **Config Files**: `config/servers.yaml`, `config/domains.yaml`
- **Secret Management**: Environment variables via python-dotenv
- **Required Env Vars**: `IONOS_API_KEY`, `ACME_EMAIL`, `RENEWAL_THRESHOLD_DAYS`

#### Example Configuration

**servers.yaml**:
```yaml
servers:
  - name: webserver-01
    host: 192.168.1.101
    user: automation_user
    ssh_key_path: "/root/.ssh/automation_key"
    nginx_reload_command: "sudo systemctl reload nginx"
    cert_path: "/etc/nginx/ssl"
```

**domains.yaml**:
```yaml
domains:
  - domain: example.com
    servers:
      - webserver-01
      - webserver-02
```

#### Definition of Done
- YAML parsing working correctly
- Environment variable loading functional
- Configuration validation prevents invalid setups
- New domains/servers can be added by editing YAML only

---

### SSLCERT-30: Secure Certificate Deployment
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: Critical  
**Story Points**: 8  
**Sprint**: Sprint 4  
**Labels**: deployment, ssh, security, nginx

#### User Story
As an Operator, I want renewed certificates securely deployed to target servers via SSH/SCP so that certificates are automatically updated across all infrastructure.

#### Acceptance Criteria
- [ ] SSH connection uses key-based authentication only (no passwords)
- [ ] Creates backup of existing certificates before deployment
- [ ] Securely copies fullchain.cer and private key to server-defined paths via SCP
- [ ] Sets correct file permissions (cert: 644, private key: 600)
- [ ] Deployment happens to all servers mapped to the domain
- [ ] Handles SSH connection failures gracefully
- [ ] Continues to next server if one fails
- [ ] Logs all deployment actions and results

#### Technical Implementation
- **Module**: `remote_deployer.py` (to be created)
- **SSH Library**: paramiko
- **Process**:
  1. Establish SSH connection
  2. Backup existing certs: `sudo cp current.pem backup_{timestamp}.pem`
  3. Upload fullchain.cer → `/etc/nginx/ssl/fullchain.pem`
  4. Upload domain.key → `/etc/nginx/ssl/privkey.pem`
  5. Set permissions: `chmod 644 fullchain.pem && chmod 600 privkey.pem`

#### Security Requirements
- SSH key must have 600 permissions
- Use dedicated automation service account
- No password-based authentication
- Audit logging of all SSH operations

#### Definition of Done
- Certificate files successfully uploaded to all configured servers
- File permissions correctly set on remote servers
- SSH errors handled and logged
- Backup created before deployment

---

### SSLCERT-31: Nginx Validation & Reload
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: Critical  
**Story Points**: 5  
**Sprint**: Sprint 4  
**Labels**: nginx, validation, zero-downtime

#### User Story
As an Operator, I want the system to validate Nginx configuration and gracefully reload the service so that new certificates are applied without service disruption.

#### Acceptance Criteria
- [ ] Executes `nginx -t` remotely before reload
- [ ] Parses nginx -t output for success/failure
- [ ] Aborts deployment if validation fails
- [ ] Rolls back certificates if validation fails
- [ ] Gracefully reloads Nginx using configured command
- [ ] Reload preserves existing connections (zero downtime)
- [ ] Logs validation and reload results
- [ ] Reload completes within 30-second timeout

#### Technical Implementation
- **Module**: `remote_deployer.py` (add methods)
- **Validation Command**: `sudo nginx -t`
- **Reload Command**: From `servers.yaml` (e.g., `sudo systemctl reload nginx`)
- **Success Indicators**: "syntax is ok" and "test is successful"

#### Rollback on Failure
```
If nginx -t fails:
  1. Restore backup certificates
  2. Reload nginx with old certificates
  3. Log detailed error
  4. Abort deployment for this server
```

#### Zero-Downtime Reload
- Nginx receives SIGHUP signal
- Master process re-reads configuration
- New workers started with new config
- Old workers finish current requests gracefully
- Old workers shut down

#### Definition of Done
- Nginx configuration validation working
- Graceful reload implemented
- Rollback mechanism functional
- No dropped connections during reload

---

### SSLCERT-32: Post-Deployment Health Checks
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: High  
**Story Points**: 3  
**Sprint**: Sprint 4  
**Labels**: validation, health-check, monitoring

#### User Story
As an Operator, I want automated health checks after deployment to confirm the new certificate is working correctly so that I can detect issues immediately.

#### Acceptance Criteria
- [ ] Makes HTTPS request to deployed domain
- [ ] Verifies 2xx/3xx HTTP status code
- [ ] Confirms new certificate is being served
- [ ] Validates certificate expiry date (should be new)
- [ ] Checks certificate CN/SAN matches domain
- [ ] Times out after 10 seconds
- [ ] Triggers rollback if health check fails
- [ ] Logs all check results

#### Technical Implementation
- **Module**: `health_checker.py` (to be created)
- **Checks**:
  1. HTTPS connectivity (`requests.get()`)
  2. HTTP status code validation
  3. SSL certificate extraction (`ssl` module)
  4. Certificate expiry verification (should be ~90 days)
  5. Domain name validation

#### Health Check Flow
```python
1. Wait 5 seconds after nginx reload
2. Make HTTPS request to https://{domain}/
3. Verify SSL/TLS handshake successful
4. Check HTTP status 200-399
5. Extract served certificate
6. Verify expiry date is new (>60 days remaining)
7. Verify certificate matches domain
```

#### Rollback on Failure
If any health check fails:
- Restore backed-up certificates
- Reload nginx with old certificates
- Re-run health check to verify restoration
- Alert operators

#### Definition of Done
- HTTPS connectivity check working
- Certificate verification functional
- Rollback triggered on failures
- All checks logged with results

---

### SSLCERT-40: Docker Containerization
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: Medium  
**Story Points**: 3  
**Sprint**: Sprint 5  
**Labels**: docker, devops, portability

#### User Story
As an Operator, I want to run the entire system inside a Docker container so that I can deploy consistently across any environment.

#### Acceptance Criteria
- [ ] Dockerfile provided with all dependencies
- [ ] Container includes: Python, pip packages, acme.sh, OpenSSH client
- [ ] Container builds successfully
- [ ] Volumes mounted for: config, certificates, logs, SSH keys
- [ ] Environment variables passed to container
- [ ] Container runs main.py successfully
- [ ] docker-compose.yml provided for easy deployment

#### Technical Implementation
- **Base Image**: python:3.9-slim-buster
- **System Dependencies**: curl, git, openssh-client, sudo
- **Python Dependencies**: From requirements.txt
- **External Tools**: acme.sh

#### Dockerfile Structure
```dockerfile
FROM python:3.9-slim-buster
RUN apt-get update && apt-get install -y curl git openssh-client sudo
RUN curl -sL https://get.acme.sh | sh
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cert_automation cert_automation/
COPY config config/
ENV CERT_BASE_PATH=/app/certs
ENV LOG_FILE_PATH=/app/renewal.log
RUN mkdir -p /app/certs /app/logs
CMD ["python", "cert_automation/main.py"]
```

#### Volume Mounts
- `-v ./config:/app/config:ro` (read-only)
- `-v ./certs:/app/certs`
- `-v ./logs:/app/logs`
- `-v ~/.ssh:/app/ssh:ro`

#### Definition of Done
- Docker image builds without errors
- Container starts and runs main.py
- All volumes mount correctly
- Environment variables accessible in container

---

### SSLCERT-41: Operational Readiness
**Type**: Story  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: Medium  
**Story Points**: 5  
**Sprint**: Sprint 5  
**Labels**: operations, logging, monitoring, cron

#### User Story
As an Operator, I want comprehensive logging, cron scheduling, and dry-run mode so that I can operate the system safely and troubleshoot issues easily.

#### Acceptance Criteria
- [ ] Detailed timestamped logs for all operations
- [ ] Logs written to both stdout and file
- [ ] Configurable log level (DEBUG/INFO/WARNING/ERROR)
- [ ] `--dry-run` flag available for testing
- [ ] Dry-run simulates all actions without executing
- [ ] Dry-run uses Let's Encrypt staging environment
- [ ] `cron.example` file provided with scheduling examples
- [ ] Log rotation configured

#### Technical Implementation

**Logging**:
- **Module**: `logger.py` (enhance existing)
- **Format**: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- **Handlers**: StreamHandler (stdout) + FileHandler
- **Log Categories**: Certificate checks, ACME operations, SSH, deployments, health checks

**Dry-Run Mode**:
- **CLI Argument**: `--dry-run` or `-d`
- **Implementation**: Pass `dry_run=True` through all modules
- **ACME**: Use `--staging` flag for acme.sh
- **SSH**: Simulate connections, log would-be actions

**Cron Example**:
```cron
# Run daily at 3 AM UTC
0 3 * * * cd /opt/cert-automation && /usr/bin/python3 main.py >> /var/log/cert-automation/cron.log 2>&1
```

#### Definition of Done
- All operations logged with timestamps
- Log level configurable via environment
- Dry-run mode functional (no actual changes made)
- Cron example provided and tested
- Log files don't fill disk (rotation working)

---

### SSLCERT-50: GitLab CI/CD Pipeline
**Type**: Task  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: Medium  
**Story Points**: 5  
**Sprint**: Sprint 6  
**Labels**: cicd, gitlab, automation

#### Description
Set up GitLab CI/CD pipeline for automated certificate renewal with scheduled jobs and manual dry-run capability.

#### Acceptance Criteria
- [ ] `.gitlab-ci.yml` configuration complete
- [ ] Docker image build stage working
- [ ] Scheduled renewal job configured (daily 3 AM)
- [ ] Manual dry-run job available
- [ ] Environment variables configured in GitLab (masked/protected)
- [ ] SSH key management in CI/CD working
- [ ] Pipeline success/failure notifications enabled

#### Technical Implementation

**GitLab CI/CD Variables** (Settings → CI/CD → Variables):
- `IONOS_API_KEY_GITLAB` (Masked, Protected)
- `ACME_EMAIL_GITLAB` (Masked, Protected)
- `SSH_PRIVATE_KEY_GITLAB` (Masked, Protected)

**.gitlab-ci.yml Structure**:
```yaml
stages:
  - build
  - renew

build_image:
  stage: build
  script:
    - docker build -t $CI_REGISTRY_IMAGE:latest .
    - docker push $CI_REGISTRY_IMAGE:latest

cert_renewal_job:
  stage: renew
  image: $CI_REGISTRY_IMAGE:latest
  before_script:
    - Setup SSH keys from CI/CD variables
  script:
    - python cert_automation/main.py
  rules:
    - if: '$CI_PIPELINE_SOURCE == "schedule"'

dry_run_job:
  stage: renew
  script:
    - python cert_automation/main.py --dry-run
  when: manual
```

#### Schedule Configuration
- **Frequency**: Daily at 3 AM UTC
- **Target Branch**: main
- **Cron Expression**: `0 3 * * *`

#### Definition of Done
- Pipeline builds Docker image successfully
- Scheduled job runs daily at 3 AM
- Dry-run job available for manual testing
- All secrets properly configured and masked
- Pipeline logs accessible for troubleshooting

---

### SSLCERT-60: Documentation & README
**Type**: Task  
**Parent**: SSLCERT-1  
**Status**: ❌ To Do  
**Priority**: High  
**Story Points**: 3  
**Sprint**: Sprint 6  
**Labels**: documentation

#### Description
Create comprehensive README.md with setup, configuration, usage, and troubleshooting instructions.

#### Sections Required
- [ ] Project overview and features
- [ ] Prerequisites and dependencies
- [ ] Installation instructions (local, Docker, CI/CD)
- [ ] Configuration guide (YAML files, environment variables, SSH setup)
- [ ] Usage examples (manual run, dry-run, cron)
- [ ] Troubleshooting common issues
- [ ] Security best practices
- [ ] Recovery procedures
- [ ] FAQ
- [ ] Contributing guidelines

#### Key Documentation Areas

**Setup Guide**:
- Installing dependencies (Python, acme.sh)
- Creating configuration files
- Setting up SSH keys
- Configuring environment variables

**Usage Examples**:
```bash
# Manual run
python3 main.py

# Dry-run mode
python3 main.py --dry-run

# Docker
docker run --env-file .env cert-automation

# Check logs
tail -f /var/log/cert-automation/renewal.log
```

**Troubleshooting**:
- DNS propagation issues
- SSH connection failures
- Nginx validation errors
- Health check failures
- Recovery procedures

#### Definition of Done
- README.md complete and readable
- All setup steps tested and verified
- Examples working and up-to-date
- Troubleshooting guide covers common issues
- Security section complete

---

## Summary

**Total Tickets**: 10 (1 Epic + 9 Stories/Tasks)  
**Total Story Points**: 53  
**Completed**: 21 points (40%)  
**Remaining**: 32 points (60%)

**By Priority**:
- **Critical**: 3 tickets (26 points) - Core deployment and validation
- **High**: 3 tickets (16 points) - Health checks and documentation
- **Medium**: 3 tickets (13 points) - Docker, operations, CI/CD

**By Status**:
- ✅ **Done**: 2 tickets (Epic 1 & 2)
- ❌ **To Do**: 7 tickets (Epic 3, 4, and additional tasks)

**Sprint Breakdown**:
- **Sprint 1-3**: Completed (Renewal engine + Configuration)
- **Sprint 4**: Deployment, validation, health checks
- **Sprint 5**: Docker, operational readiness
- **Sprint 6**: CI/CD, documentation
