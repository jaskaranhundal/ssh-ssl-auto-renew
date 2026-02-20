#!/usr/bin/env bash
set -euo pipefail

# Example safe renewal workflow.
# Adapt paths/services for your environment before production use.
CERTBOT_BIN="${CERTBOT_BIN:-certbot}"
SERVICE_NAME="${SERVICE_NAME:-nginx}"
DOMAIN="${DOMAIN:-example.com}"
MIN_REMAINING_DAYS="${MIN_REMAINING_DAYS:-15}"

log() { printf '%s %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }

check_expiry_days() {
  local end_date now_ts end_ts remaining
  end_date=$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" | cut -d= -f2 || true)
  if [[ -z "${end_date}" ]]; then
    echo 0
    return
  fi
  now_ts=$(date +%s)
  end_ts=$(date -j -f "%b %e %T %Y %Z" "$end_date" +%s 2>/dev/null || date -d "$end_date" +%s)
  remaining=$(( (end_ts - now_ts) / 86400 ))
  echo "$remaining"
}

main() {
  local remaining_days
  remaining_days=$(check_expiry_days)

  if [[ "$remaining_days" -gt "$MIN_REMAINING_DAYS" ]]; then
    log "Certificate has ${remaining_days} days remaining; skipping renewal"
    exit 0
  fi

  log "Starting renewal for ${DOMAIN}"
  "$CERTBOT_BIN" renew --quiet --cert-name "$DOMAIN"

  log "Reloading ${SERVICE_NAME}"
  systemctl reload "$SERVICE_NAME"

  if ! openssl s_client -servername "$DOMAIN" -connect "${DOMAIN}:443" -brief </dev/null >/dev/null 2>&1; then
    log "Post-renew TLS validation failed; manual rollback required"
    exit 1
  fi

  log "Renewal and validation completed successfully"
}

main "$@"
