# Dockerfile for the Automated SSL Certificate Renewal System
# This file packages the application and its dependencies into a container image.

# Use a slim Python base image
FROM python:3.10-slim

# Set working directory inside the container
WORKDIR /app

# Install system dependencies
# - curl is needed to install acme.sh
# - git is a dependency for acme.sh for some operations
# - openssh-client is needed for the ssh/scp operations via paramiko
RUN apt-get update && apt-get install -y --no-install-recommends 
    curl 
    git 
    openssh-client 
    && rm -rf /var/lib/apt/lists/*

# Install acme.sh
# This will install it to /root/.acme.sh/
RUN curl https://get.acme.sh | sh -s -- --home /acme.sh
ENV PATH="/acme.sh:${PATH}"

# Copy the application requirements file
COPY cert_automation/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY cert_automation/ .

# Set up volumes for persistent data and configuration
# These should be mounted by the user when running the container.
# - /app/config: To provide servers.yaml and domains.yaml
# - /certs: To store the issued certificates persistently
# - /root/.ssh: To provide the SSH private key for deployment
VOLUME /app/config
VOLUME /certs
VOLUME /root/.ssh

# Set environment variables from the .env file when running the container.
# Example: docker run -v ... --env-file ./cert_automation/.env ssl-automation
# The default CERT_BASE_PATH is set to /certs to align with the volume.
ENV CERT_BASE_PATH="/certs"
ENV ACME_HOME_DIR="/acme.sh"

# Define the entrypoint for the container
ENTRYPOINT ["python3", "main.py"]
