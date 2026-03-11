#!/bin/bash

# Configuration
USER_NAME="jaskarn_singh"  # Change to auto_ssl_user if needed
KEY_PATH="/Users/jaskarn.singh/.ssh/id_rsa"
HOSTS=("10.0.0.15" "10.0.0.10" "10.0.0.9" "10.0.0.14" "10.0.0.8" "10.0.0.13" "10.0.0.3" "10.0.0.2")

echo "================================================================"
echo "LINDERA INFRASTRUCTURE SSL SCAN"
echo "Starting at: $(date)"
echo "================================================================"

for host in "${HOSTS[@]}"; do
    echo ""
    echo ">>> SCANNING HOST: $host"
    echo "----------------------------------------------------------------"
    
    # Check if host is reachable
    if ! ping -c 1 -W 1 "$host" > /dev/null 2>&1; then
        echo "[!] SKIP: Host $host is not reachable via ping."
        continue
    fi

    # Attempt to extract Nginx SSL config
    # We search in standard Nginx paths and also gitlab.rb for the gitlab host
    ssh -i "$KEY_PATH" -o ConnectTimeout=5 -o StrictHostKeyChecking=no "$USER_NAME@$host" \
    "sudo grep -rE 'server_name|ssl_certificate|ssl_certificate_key' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ /etc/gitlab/gitlab.rb 2>/dev/null | grep -v '#'" \
    || echo "[X] ERROR: Connection or Permission failed for $host"

    echo "----------------------------------------------------------------"
done

echo ""
echo "================================================================"
echo "Scan Complete."
echo "================================================================"
