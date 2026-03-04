# Dockerfile for the Automated SSL Certificate Renewal System
# This file packages the application and its dependencies into a container image.

# Use a slim Python base image
FROM python:3.10-slim-buster

# Create a non-root user
ARG UID=1000
RUN adduser --system --uid ${UID} certuser

# Set working directory inside the container
WORKDIR /app

# Install system dependencies
# - curl is needed to install acme.sh
# - git is a dependency for acme.sh
# - socat is often required by acme.sh
# - openssh-client is needed for paramiko operations
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    socat \
    openssh-client \
    sudo \
    # Clean up apt cache
    && rm -rf /var/lib/apt/lists/*

# Install acme.sh for the certuser
RUN curl https://get.acme.sh | sh -s -- --install --home /home/certuser/.acme.sh \
    --accountemail "jaskarn.singh@lindera.de"

# Add acme.sh to PATH
ENV PATH="/home/certuser/.acme.sh:${PATH}"
# Explicitly set the command path for the Python script
ENV ACME_SH_COMMAND="/home/certuser/.acme.sh/acme.sh"

# Copy application requirements
COPY cert_automation/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY cert_automation/ .

# Ensure necessary directories exist and have correct ownership
RUN mkdir -p /app/logs /app/reports /app/certs \
    && chown -R certuser:certuser /app \
    && chown -R certuser:certuser /home/certuser/.acme.sh

# Set environment variables
ENV CERT_BASE_PATH="/app/certs"
ENV ACME_HOME_DIR="/home/certuser/.acme.sh"
ENV LOG_FILE_PATH="/app/logs/renewal.log"
ENV REPORT_FILE_PATH="/app/reports/renewal_report.md"

# Switch to the non-root user
USER certuser

# Define the entrypoint for the container
ENTRYPOINT ["python3", "main.py"]

# Add a HEALTHCHECK instruction
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 CMD python3 -c "import os; exit(0 if os.path.exists('/app/main.py') else 1)"