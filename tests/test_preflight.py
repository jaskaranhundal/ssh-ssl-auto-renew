from unittest.mock import MagicMock, patch

import pytest

from cert_automation import preflight as pf


# ---------------- _parse_expiry ----------------

@pytest.mark.parametrize("text,expected", [
    ("Password expires : never", pf.PASS),
    ("Password expires : Jun 01, 2020", pf.FAIL),       # clearly past
    ("Password expires : Jan 01, 2099", pf.PASS),       # far future
    ("nothing here", pf.WARN),
    ("Password expires : not-a-date", pf.WARN),
])
def test_parse_expiry(text, expected):
    status, _ = pf._parse_expiry(text)
    assert status == expected


# ---------------- diagnose_network ----------------

def test_diagnose_network_port_probe_and_missing_binaries():
    # 443 open, 22/80 closed; no ping/traceroute binaries
    def fake_tcp(host, port, timeout=8):
        return port == 443
    with patch("cert_automation.preflight._tcp_open", side_effect=fake_tcp), \
         patch("cert_automation.preflight.shutil.which", return_value=None):
        out = pf.diagnose_network("192.0.2.99")
    assert "tcp open: [443]" in out
    assert "ping: n/a" in out and "traceroute: n/a" in out


# ---------------- check_host ----------------

def _deployer_mock(responses):
    dep = MagicMock()
    dep._connect.return_value = True

    def _runner(cmd, check_exit_code=True):
        for key, val in responses.items():
            if key in cmd:
                if isinstance(val, Exception):
                    raise val
                return val
        return ""
    dep.execute_command.side_effect = _runner
    return dep


HEALTHY = {
    "chage -l": "Password expires : never",
    "test -d": "EXISTS",
    "server_name": "/etc/nginx/sites-enabled/x",
    "ssl_certificate ": "ssl_certificate /opt/app/ssl/fullchain.pem;",
}


def test_all_pass():
    srv = {"name": "s1", "host": "192.0.2.9", "cert_path": "/opt/app/ssl", "user": "u"}
    with patch("cert_automation.preflight._tcp_open", return_value=True), \
         patch("cert_automation.preflight.RemoteDeployer", return_value=_deployer_mock(HEALTHY)):
        r = pf.check_host(srv, "/k", ["app.example.com"], {"192.0.2.9": True})
    assert r["ok"] is True
    statuses = {c["name"]: c["status"] for c in r["checks"]}
    assert statuses["tcp_22"] == pf.PASS and statuses["nginx_ssl_path"] == pf.PASS


def test_tcp_unreachable_short_circuits():
    srv = {"name": "s", "host": "198.51.100.3", "cert_path": "/x", "user": "u"}
    with patch("cert_automation.preflight._tcp_open", return_value=False), \
         patch("cert_automation.preflight.diagnose_network", return_value="ping: NO reply | tcp open: none"):
        r = pf.check_host(srv, "/k", ["d"], {"198.51.100.3": True})
    assert r["ok"] is False and "tcp_22" in r["reason"]
    statuses = {c["name"]: c["status"] for c in r["checks"]}
    assert statuses["ssh_auth"] == pf.SKIP


def test_ssh_auth_fail_blocks():
    srv = {"name": "s", "host": "192.0.2.13", "cert_path": "/x", "user": "u"}
    dep = _deployer_mock({})
    dep._connect.side_effect = Exception("EOF during negotiation")
    with patch("cert_automation.preflight._tcp_open", return_value=True), \
         patch("cert_automation.preflight.RemoteDeployer", return_value=dep):
        r = pf.check_host(srv, "/k", ["d"], {"192.0.2.13": True})
    assert r["ok"] is False and "ssh_auth" in r["reason"]


def test_expired_account_is_warn_not_blocking():
    # Expired account surfaces as ssh_auth/EOF anyway — account_expiry is advisory.
    responses = dict(HEALTHY, **{"chage -l": "Password expires : Jun 01, 2020"})
    srv = {"name": "s", "host": "192.0.2.13", "cert_path": "/opt/app/ssl", "user": "u"}
    with patch("cert_automation.preflight._tcp_open", return_value=True), \
         patch("cert_automation.preflight.RemoteDeployer", return_value=_deployer_mock(responses)):
        r = pf.check_host(srv, "/k", ["app.example.com"], {"192.0.2.13": True})
    statuses = {c["name"]: c["status"] for c in r["checks"]}
    assert statuses["account_expiry"] == pf.WARN
    assert r["ok"] is True


def test_cert_path_missing_is_warn_not_blocking():
    responses = dict(HEALTHY, **{"test -d": "NO"})
    srv = {"name": "s", "host": "192.0.2.4", "cert_path": "/opt/missing/ssl", "user": "u"}
    with patch("cert_automation.preflight._tcp_open", return_value=True), \
         patch("cert_automation.preflight.RemoteDeployer", return_value=_deployer_mock(responses)):
        r = pf.check_host(srv, "/k", ["app.example.com"], {"192.0.2.4": True})
    statuses = {c["name"]: c["status"] for c in r["checks"]}
    assert statuses["cert_path"] == pf.WARN
    assert r["ok"] is True   # advisory, not blocking


def test_nginx_path_mismatch_warn():
    responses = dict(HEALTHY, **{"ssl_certificate ": "ssl_certificate /opt/OTHER/ssl/fullchain.pem;"})
    srv = {"name": "s", "host": "192.0.2.4", "cert_path": "/opt/app/ssl", "user": "u"}
    with patch("cert_automation.preflight._tcp_open", return_value=True), \
         patch("cert_automation.preflight.RemoteDeployer", return_value=_deployer_mock(responses)):
        r = pf.check_host(srv, "/k", ["app.example.com"], {"192.0.2.4": True})
    statuses = {c["name"]: c["status"] for c in r["checks"]}
    assert statuses["nginx_ssl_path"] == pf.WARN
    assert r["ok"] is True


# ---------------- report + helpers ----------------

def test_report_and_blocking_set():
    results = [
        {"name": "ok1", "host": "1.1.1.1", "cert_path": "/x", "ok": True,
         "reason": "", "checks": [{"name": "tcp_22", "status": pf.PASS, "detail": ""}]},
        {"name": "bad1", "host": "2.2.2.2", "cert_path": "/x", "ok": False,
         "reason": "ssh_auth: EOF", "checks": [{"name": "ssh_auth", "status": pf.FAIL, "detail": "EOF"}]},
    ]
    md = pf.generate_preflight_report(results)
    assert "Blocking failures: 1" in md and "bad1" in md and "ssh_auth" in md
    assert pf.blocking_failed_hosts(results) == {"bad1"}


def test_run_preflight_only_referenced_servers():
    servers = {"servers": [{"name": "a", "host": "1.1.1.1", "cert_path": "/x"},
                           {"name": "unused", "host": "9.9.9.9"}]}
    domains = {"domains": [{"domain": "d", "servers": ["a"]}]}
    with patch("cert_automation.preflight.check_host",
               return_value={"name": "a", "host": "1.1.1.1", "cert_path": "/x",
                             "ok": True, "reason": "", "checks": []}):
        res = pf.run_preflight(servers, domains, "/k", {"1.1.1.1": True})
    assert [r["name"] for r in res] == ["a"]   # 'unused' skipped (no domain)


# ---------------- teams preflight card ----------------

def test_teams_preflight_card():
    from cert_automation import teams_notifier as tn
    results = [{"name": "bad", "host": "2.2.2.2", "ok": False, "reason": "tcp_22: unreachable",
                "checks": [{"name": "tcp_22", "status": "FAIL", "detail": "x"}]}]
    card = tn.build_preflight_card(results)
    body = card["attachments"][0]["content"]["body"]
    assert body[0]["text"] == "Pre-flight Diagnostics — FAILURE"
    assert any(b.get("type") == "FactSet" and b["facts"][0]["title"] == "bad" for b in body)
