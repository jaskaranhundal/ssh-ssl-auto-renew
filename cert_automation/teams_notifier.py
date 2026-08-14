"""Microsoft Teams notifier for SSL renewal runs.

Posts an Adaptive Card to a Power Automate **Workflow** HTTP trigger (the modern
replacement for the retiring O365 Incoming Webhook connector). The webhook URL is a
signed secret and must come from the ``TEAMS_WEBHOOK_URL`` environment variable —
never hardcode it.

Entry point: ``notify(results, report_markdown=None)``. Best-effort: any failure here
is logged and swallowed so it can never change the renewal exit code.
"""
import os
import socket
import logging
from datetime import datetime
from urllib.parse import urlparse

import requests

from retry_decorator import retry

log = logging.getLogger(__name__)


def _host_resolves(webhook_url: str) -> bool:
    """True if the webhook URL's host resolves via DNS. Lets us skip cleanly (no retries)
    when the endpoint is unreachable/unresolvable instead of burning retry attempts."""
    host = urlparse(webhook_url).hostname
    if not host:
        return False
    try:
        socket.getaddrinfo(host, None)
        return True
    except socket.gaierror:
        return False


def _overall_status(results: dict) -> str:
    """Mirror report_generator's status logic."""
    failed = results.get("failed_renewals", [])
    if failed:
        if len(failed) == results.get("total_domains_configured", 0):
            return "FAILURE"
        return "PARTIAL_SUCCESS"
    if results.get("total_domains_configured", 0) == 0 and results.get("domains_processed", 0) == 0:
        return "NO_DOMAINS_CONFIGURED"
    return "SUCCESS"


_STATUS_COLOR = {
    "SUCCESS": ("Good", "good"),
    "PARTIAL_SUCCESS": ("Warning", "warning"),
    "FAILURE": ("Attention", "attention"),
    "NO_DOMAINS_CONFIGURED": ("Default", "default"),
}


def _failure_facts(results: dict):
    """One fact per failed (domain -> server: error)."""
    facts = []
    for f in results.get("failed_renewals", []):
        domain = f.get("domain", "unknown")
        if f.get("issue_error"):
            facts.append({"title": domain, "value": f"issuance: {f['issue_error']}"})
        for dr in f.get("deployment_results", []):
            if not dr.get("success", False):
                facts.append({"title": domain,
                              "value": f"{dr.get('server', '?')}: {dr.get('message', 'failed')}"})
    return facts


def _report_filename(results: dict, status: str) -> str:
    end = results.get("end_time") or datetime.now()
    kind = "dryrun" if results.get("dry_run") else "live"
    return f"renewal_report_{kind}_{status.lower()}_{end.strftime('%Y%m%d_%H%M%S')}.md"


def build_card(results: dict, report_markdown: str = None) -> dict:
    """Build the Power Automate Workflow message envelope with one Adaptive Card.

    When ``report_markdown`` is provided, the full report is included under a top-level
    ``report`` field (filename + content) so the Power Automate flow can write it to
    SharePoint/OneDrive and post it as a real Teams file attachment.
    """
    status = _overall_status(results)
    text_color, _ = _STATUS_COLOR.get(status, ("Default", "default"))
    run_kind = "DRY RUN" if results.get("dry_run") else "LIVE"
    end = results.get("end_time") or datetime.now()
    job = os.getenv("CI_JOB_NAME", "renewal")
    job_id = os.getenv("CI_JOB_ID", "")
    ref = os.getenv("CI_COMMIT_REF_NAME", "")
    ci_job_url = os.getenv("CI_JOB_URL", "")

    subtitle = f"{run_kind} · {job}{(' #' + job_id) if job_id else ''}{(' @ ' + ref) if ref else ''} · {results.get('duration', 'N/A')}"

    body = [
        {"type": "TextBlock", "size": "Large", "weight": "Bolder", "color": text_color,
         "text": f"SSL Renewal — {status}"},
        {"type": "TextBlock", "isSubtle": True, "spacing": "None", "wrap": True,
         "text": f"{subtitle} · {end.strftime('%Y-%m-%d %H:%M:%S')}"},
        {"type": "FactSet", "facts": [
            {"title": "Configured", "value": str(results.get("total_domains_configured", 0))},
            {"title": "Processed", "value": str(results.get("domains_processed", 0))},
            {"title": "Succeeded", "value": str(len(results.get("successful_renewals", [])))},
            {"title": "Skipped", "value": str(len(results.get("skipped_renewals", [])))},
            {"title": "Failed", "value": str(len(results.get("failed_renewals", [])))},
        ]},
    ]

    fail_facts = _failure_facts(results)
    if fail_facts:
        body.append({"type": "TextBlock", "weight": "Bolder", "spacing": "Medium",
                     "text": "Failed deployments"})
        body.append({"type": "FactSet", "facts": fail_facts})

    report_name = _report_filename(results, status) if report_markdown else None
    if report_name:
        body.append({"type": "TextBlock", "isSubtle": True, "spacing": "Medium", "wrap": True,
                     "text": f"Full report attached: {report_name}"})

    card = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
    actions = []
    if ci_job_url:
        actions.append({"type": "Action.OpenUrl", "title": "Open CI job", "url": ci_job_url})
    # Link to the report archived as a GitLab CI artifact. Explicit REPORT_ARTIFACT_URL wins;
    # otherwise build the standard <job>/artifacts/file/<path> URL from CI_JOB_URL.
    report_url = os.getenv("REPORT_ARTIFACT_URL") or (
        f"{ci_job_url}/artifacts/file/{os.getenv('REPORT_ARTIFACT_PATH', 'reports/renewal_report.md')}"
        if ci_job_url else None)
    if report_url:
        actions.append({"type": "Action.OpenUrl", "title": "Download report", "url": report_url})
    if actions:
        card["actions"] = actions

    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": card,
        }],
    }
    if report_markdown:
        # The Power Automate flow reads this to create the file attachment.
        payload["report"] = {
            "filename": report_name,
            "content_type": "text/markdown",
            "markdown": report_markdown,
        }
    return payload


@retry(tries=3, delay=2, backoff=2, jitter=1.0,
       exceptions=(requests.exceptions.RequestException,))
def _post(webhook_url: str, payload: dict) -> None:
    resp = requests.post(webhook_url, json=payload,
                         headers={"Content-Type": "application/json"}, timeout=30)
    resp.raise_for_status()  # Power Automate returns 202 Accepted on success (a 2xx)


def notify(results: dict, report_markdown: str = None) -> bool:
    """Send the renewal summary to Teams. Returns True if sent, False otherwise.

    - No-op (returns False) if TEAMS_ENABLED is false or TEAMS_WEBHOOK_URL is unset.
    - Always sends on failure; sends on all-success only if NOTIFY_ON_SUCCESS is true.
    - Never raises — notification problems must not affect the renewal outcome.
    """
    enabled = os.getenv("TEAMS_ENABLED", "true").lower() == "true"
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    notify_success = os.getenv("NOTIFY_ON_SUCCESS", "true").lower() == "true"

    if not enabled:
        log.info("Teams notifications disabled (TEAMS_ENABLED=false).")
        return False
    if not webhook_url:
        log.info("Teams notifications skipped: TEAMS_WEBHOOK_URL not set.")
        return False
    if not _host_resolves(webhook_url):
        log.warning("Teams notifications skipped: webhook host does not resolve.")
        return False

    has_failures = bool(results.get("failed_renewals"))
    if not has_failures and not notify_success:
        log.info("Teams: run succeeded and NOTIFY_ON_SUCCESS=false — not sending.")
        return False

    try:
        _post(webhook_url, build_card(results, report_markdown))
        log.info("Teams notification sent.")
        return True
    except Exception as e:  # noqa: BLE001 - best effort, must not break the run
        log.error(f"Teams notification failed (ignored): {e}")
        return False


def build_preflight_card(preflight_results: list) -> dict:
    """Adaptive Card summarising the SSH/deploy pre-flight diagnostics."""
    n_fail = sum(1 for r in preflight_results if not r.get("ok"))
    n_warn = sum(1 for r in preflight_results
                 if r.get("ok") and any(c.get("status") == "WARN" for c in r.get("checks", [])))
    status = "FAILURE" if n_fail else ("WARNINGS" if n_warn else "OK")
    text_color = {"FAILURE": "Attention", "WARNINGS": "Warning", "OK": "Good"}[status]
    ci_job_url = os.getenv("CI_JOB_URL", "")
    ref = os.getenv("CI_COMMIT_REF_NAME", "")

    facts = [{"title": r["name"], "value": f"{r['host']} — {r['reason']}"}
             for r in preflight_results if not r.get("ok")]
    for r in preflight_results:
        if r.get("ok"):
            warns = [c for c in r.get("checks", []) if c.get("status") == "WARN"]
            if warns:
                facts.append({"title": r["name"],
                              "value": "; ".join(f"{c['name']}: {c['detail']}" for c in warns)})

    body = [
        {"type": "TextBlock", "size": "Large", "weight": "Bolder", "color": text_color,
         "text": f"Pre-flight Diagnostics — {status}"},
        {"type": "TextBlock", "isSubtle": True, "spacing": "None", "wrap": True,
         "text": f"{len(preflight_results)} hosts · {n_fail} blocking · {n_warn} warnings"
                 + (f" · @ {ref}" if ref else "")},
    ]
    if facts:
        body.append({"type": "FactSet", "facts": facts})

    card = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard", "version": "1.4", "body": body}
    actions = []
    if ci_job_url:
        actions.append({"type": "Action.OpenUrl", "title": "Open CI job", "url": ci_job_url})
        actions.append({"type": "Action.OpenUrl", "title": "Download report",
                        "url": f"{ci_job_url}/artifacts/file/reports/preflight_report.md"})
    if actions:
        card["actions"] = actions
    return {"type": "message",
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                             "content": card}]}


def notify_preflight(preflight_results: list) -> bool:
    """Post the pre-flight summary to Teams. Same gating/skip rules as notify()."""
    enabled = os.getenv("TEAMS_ENABLED", "true").lower() == "true"
    webhook_url = os.getenv("TEAMS_WEBHOOK_URL")
    notify_success = os.getenv("NOTIFY_ON_SUCCESS", "true").lower() == "true"

    if not enabled or not webhook_url or not _host_resolves(webhook_url):
        log.info("Pre-flight Teams notification skipped (disabled/unset/unresolvable).")
        return False

    has_fail = any(not r.get("ok") for r in preflight_results)
    if not has_fail and not notify_success:
        log.info("Pre-flight all-clear and NOTIFY_ON_SUCCESS=false — not sending.")
        return False

    try:
        _post(webhook_url, build_preflight_card(preflight_results))
        log.info("Pre-flight Teams notification sent.")
        return True
    except Exception as e:  # noqa: BLE001
        log.error(f"Pre-flight Teams notification failed (ignored): {e}")
        return False
