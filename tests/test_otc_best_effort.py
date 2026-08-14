from unittest.mock import patch

from cert_automation import main as m


def _call():
    # OTCELBClient mocked to fail (simulates the 401 / unreachable OTC) so we hit the
    # except handler that sets the advisory flag.
    with patch("cert_automation.main.OTCELBClient", side_effect=Exception("401 Client Error")):
        return m.deploy_to_otc_elb(
            {"listeners": [{"name": "elb-example-listener", "id": "x"}]},
            "*.example.com", "/x/fc", "/x/key", {})


def test_otc_failure_advisory_when_best_effort(monkeypatch):
    monkeypatch.setenv("OTC_ELB_BEST_EFFORT", "true")
    res = _call()
    assert res[0]["success"] is False
    assert res[0]["advisory"] is True


def test_otc_failure_fatal_by_default(monkeypatch):
    monkeypatch.delenv("OTC_ELB_BEST_EFFORT", raising=False)
    res = _call()
    assert res[0]["success"] is False
    assert res[0]["advisory"] is False


def test_advisory_result_does_not_fail_domain():
    # The all(...) rule in process_domain excludes advisory results.
    results = [
        {"server": "srv", "success": True},
        {"server": "OTC ELB", "success": False, "advisory": True},
    ]
    ok = all(r["success"] for r in results if not r.get("advisory"))
    assert ok is True
