from datetime import datetime
from unittest.mock import patch

from cert_automation import teams_notifier as tn


def _results(failed=0, configured=5, succeeded=5):
    failures = [{"domain": f"d{i}.example.com",
                 "issue_error": None,
                 "deployment_results": [{"server": "srv", "success": False, "message": "host key not in known_hosts"}]}
                for i in range(failed)]
    return {
        "total_domains_configured": configured,
        "domains_processed": configured,
        "successful_renewals": [f"ok{i}" for i in range(succeeded)],
        "skipped_renewals": [],
        "failed_renewals": failures,
        "dry_run": False,
        "duration": "0h 1m 2s",
        "end_time": datetime(2026, 6, 12, 12, 0, 0),
    }


def test_build_card_envelope_and_status():
    card = tn.build_card(_results(failed=2, configured=5))
    assert card["type"] == "message"
    att = card["attachments"][0]
    assert att["contentType"] == "application/vnd.microsoft.card.adaptive"
    body = att["content"]["body"]
    assert body[0]["text"] == "SSL Renewal — PARTIAL_SUCCESS"
    # failed-domain FactSet present
    assert any(b.get("type") == "FactSet" and any("host key" in f["value"] for f in b["facts"]) for b in body)


def test_build_card_embeds_report_when_provided():
    md = "# SSL Certificate Renewal Report\n- api.example.com failed\n"
    card = tn.build_card(_results(failed=1), report_markdown=md)
    assert card["report"]["markdown"] == md
    assert card["report"]["filename"].endswith(".md")
    assert card["report"]["content_type"] == "text/markdown"
    # card mentions the attachment
    body = card["attachments"][0]["content"]["body"]
    assert any("Full report attached" in b.get("text", "") for b in body)


def test_build_card_no_report_field_without_markdown():
    card = tn.build_card(_results(failed=1))
    assert "report" not in card


def test_download_report_action_from_ci_job_url(monkeypatch):
    monkeypatch.setenv("CI_JOB_URL", "https://gitlab.example.com/g/p/-/jobs/99")
    monkeypatch.delenv("REPORT_ARTIFACT_URL", raising=False)
    actions = tn.build_card(_results(failed=1))["attachments"][0]["content"]["actions"]
    titles = {a["title"]: a["url"] for a in actions}
    assert titles["Open CI job"] == "https://gitlab.example.com/g/p/-/jobs/99"
    assert titles["Download report"] == \
        "https://gitlab.example.com/g/p/-/jobs/99/artifacts/file/reports/renewal_report.md"


def test_explicit_report_artifact_url_wins(monkeypatch):
    monkeypatch.setenv("CI_JOB_URL", "https://gitlab.example.com/g/p/-/jobs/99")
    monkeypatch.setenv("REPORT_ARTIFACT_URL", "https://files.example.com/report.md")
    actions = tn.build_card(_results(failed=1))["attachments"][0]["content"]["actions"]
    assert any(a["url"] == "https://files.example.com/report.md" for a in actions)


def test_notify_skips_when_disabled(monkeypatch):
    monkeypatch.setenv("TEAMS_ENABLED", "false")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.com/x")
    assert tn.notify(_results(failed=1)) is False


def test_notify_skips_when_url_unset(monkeypatch):
    monkeypatch.delenv("TEAMS_WEBHOOK_URL", raising=False)
    monkeypatch.setenv("TEAMS_ENABLED", "true")
    assert tn.notify(_results(failed=1)) is False


def test_notify_skips_when_host_unresolvable(monkeypatch):
    monkeypatch.setenv("TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://nope.invalid/x")
    with patch("cert_automation.teams_notifier._host_resolves", return_value=False) as hr, \
         patch("cert_automation.teams_notifier.requests.post") as post:
        assert tn.notify(_results(failed=1)) is False
        hr.assert_called_once()
        post.assert_not_called()


def test_notify_suppressed_on_success_when_flag_false(monkeypatch):
    monkeypatch.setenv("TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.com/x")
    monkeypatch.setenv("NOTIFY_ON_SUCCESS", "false")
    with patch("cert_automation.teams_notifier._host_resolves", return_value=True), \
         patch("cert_automation.teams_notifier.requests.post") as post:
        assert tn.notify(_results(failed=0)) is False
        post.assert_not_called()


def test_notify_sends_on_failure(monkeypatch):
    monkeypatch.setenv("TEAMS_ENABLED", "true")
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://example.com/x")
    with patch("cert_automation.teams_notifier._host_resolves", return_value=True), \
         patch("cert_automation.teams_notifier.requests.post") as post:
        post.return_value.raise_for_status.return_value = None
        post.return_value.status_code = 202
        assert tn.notify(_results(failed=2)) is True
        post.assert_called_once()
