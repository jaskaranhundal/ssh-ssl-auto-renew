# Dockerfile for the Automated SSL Certificate Renewal System
# This file packages the application and its dependencies into a container image.

# Use a slim Python base image (Updated to Bookworm for repository support)
FROM python:3.10-slim-bookworm

# Create a non-root user and group
ARG UID=1000
RUN groupadd --system --gid ${UID} certuser && \
    useradd --system --uid ${UID} --gid certuser --create-home certuser

# Set working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    socat \
    openssh-client \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Ensure home directory exists and is owned by certuser before switching
RUN mkdir -p /home/certuser/.acme.sh && chown -R certuser:certuser /home/certuser

# Switch to certuser for acme.sh installation
USER certuser
RUN curl https://get.acme.sh | sh -s -- --install --home /home/certuser/.acme.sh \
    --accountemail "jaskarn.singh@lindera.de"

# Switch back to root for global symlink and dependencies
USER root
RUN ln -s /home/certuser/.acme.sh/acme.sh /usr/local/bin/acme.sh
COPY cert_automation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY cert_automation/ .

# Ensure necessary directories exist and have correct ownership
RUN mkdir -p /app/logs /app/reports /app/certs && \
    chown -R certuser:certuser /app && \
    chown -R certuser:certuser /home/certuser

# Set environment variables
ENV CERT_BASE_PATH="/app/certs"
ENV ACME_HOME_DIR="/home/certuser/.acme.sh"
ENV LOG_FILE_PATH="/app/logs/renewal.log"
ENV REPORT_FILE_PATH="/app/reports/renewal_report.md"

# Switch back to the non-root user
USER certuser

# Define the entrypoint for the container
ENTRYPOINT ["python3", "main.py"]

# Add a HEALTHCHECK instruction
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD python3 -c "import os; exit(0 if os.path.exists('/app/main.py') else 1)"